import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from cache import get_cached_product, set_job_status, get_product_age_seconds
from models.schemas import ProductSubmitRequest, SubmitResponse, EnrichedProduct
from models.db_models import Product, NutritionFacts, ExtractedClaim, ExtractionSource
from worker.celery_app import analyze_product_task
from config import get_settings

router   = APIRouter()
settings = get_settings()


def make_product_id(platform: str, platform_id: str) -> str:
    return f"{platform}:{platform_id}"


@router.post("/products/submit", response_model=SubmitResponse)
async def submit_product(
    payload: ProductSubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Called by extension on every product page load.

    1. Upsert Product row (ASIN + all DOM fields)
    2. Upsert NutritionFacts if present
    3. Insert new ExtractedClaims (deduplicated)
    4. Check Redis cache — HIT returns enriched data immediately
    5. MISS — enqueue Celery job for claim verification
    """
    platform    = payload.platform.replace("https://www.", "").replace("/", "")
    platform_id = payload.platform_id
    product_key = make_product_id(platform, platform_id)

    # ── 1. Upsert Product ────────────────────────────────────────────────────
    result  = await db.execute(select(Product).where(Product.id == product_key))
    product = result.scalar_one_or_none()

    if product:
        # Update mutable fields on revisit
        product.product_name      = payload.product_name or product.product_name
        product.brand             = payload.brand        or product.brand
        product.url               = payload.url
        product.primary_image_url = payload.primary_image_url or product.primary_image_url
        from datetime import datetime, timezone
        product.last_extracted_at = datetime.now(timezone.utc)
    else:
        product = Product(
            id                = product_key,
            platform_id       = platform_id,
            platform_name     = platform,
            product_name      = payload.product_name,
            brand             = payload.brand,
            url               = payload.url,
            primary_image_url = payload.primary_image_url,
        )
        db.add(product)

    await db.flush()  # get product.id before FK inserts

    # ── 2. Upsert NutritionFacts ─────────────────────────────────────────────
    if payload.nutrition_facts:
        nf_result = await db.execute(
            select(NutritionFacts).where(NutritionFacts.product_id == product_key)
        )
        nf = nf_result.scalar_one_or_none()
        facts = payload.nutrition_facts

        qty   = payload.quantity_g
        price = payload.price_inr

        if nf:
            # Only upgrade existing DOM data — don't overwrite OCR-verified values
            if nf.source == ExtractionSource.extension_dom:
                nf.energy_kcal     = facts.energy_kcal     or nf.energy_kcal
                nf.protein_g       = facts.protein_g       or nf.protein_g
                nf.total_fat_g     = facts.total_fat_g     or nf.total_fat_g
                nf.saturated_fat_g = facts.saturated_fat_g or nf.saturated_fat_g
                nf.carbohydrates_g = facts.carbohydrates_g or nf.carbohydrates_g
                nf.sugar_g         = facts.sugar_g         or nf.sugar_g
                nf.dietary_fiber_g = facts.dietary_fiber_g or nf.dietary_fiber_g
                nf.sodium_mg       = facts.sodium_mg       or nf.sodium_mg
                nf.cholesterol_mg  = facts.cholesterol_mg  or nf.cholesterol_mg
        else:
            protein_per_rs = None
            if facts.protein_g and qty and price:
                protein_per_rs = round((facts.protein_g / (payload.serving_size_g or 30)) * qty / price * 100, 2)

            nf = NutritionFacts(
                product_id       = product_key,
                price_inr        = price,
                quantity_g       = qty,
                price_per_100g   = payload.price_per_100g,
                serving_size_g   = payload.serving_size_g,
                energy_kcal      = facts.energy_kcal,
                protein_g        = facts.protein_g,
                total_fat_g      = facts.total_fat_g,
                saturated_fat_g  = facts.saturated_fat_g,
                carbohydrates_g  = facts.carbohydrates_g,
                sugar_g          = facts.sugar_g,
                dietary_fiber_g  = facts.dietary_fiber_g,
                sodium_mg        = facts.sodium_mg,
                cholesterol_mg   = facts.cholesterol_mg,
                protein_per_rs100 = protein_per_rs,
                source           = ExtractionSource.extension_dom,
                confidence       = 0.5,
            )
            db.add(nf)

    # ── 3. Insert ExtractedClaims (skip duplicates) ──────────────────────────
    if payload.claims:
        existing_claims = await db.execute(
            select(ExtractedClaim.raw_text).where(ExtractedClaim.product_id == product_key)
        )
        existing_texts = {r[0] for r in existing_claims.fetchall()}

        for claim in payload.claims:
            if claim.text not in existing_texts:
                db.add(ExtractedClaim(
                    product_id  = product_key,
                    raw_text    = claim.text,
                    model_version = "dom_extracted",
                ))
                existing_texts.add(claim.text)

    await db.commit()

    # ── 4. Cache check ───────────────────────────────────────────────────────
    cached = await get_cached_product(platform, platform_id)

    if cached:
        age      = await get_product_age_seconds(platform, platform_id)
        is_stale = age and age > settings.stale_after_seconds

        if is_stale:
            job_id = str(uuid.uuid4())
            await set_job_status(job_id, "queued")
            analyze_product_task.delay(job_id, payload.model_dump(), product_key, refresh=True)

        return SubmitResponse(cached=True, data=EnrichedProduct(**cached))

    # ── 5. Enqueue claim verification job ────────────────────────────────────
    job_id = str(uuid.uuid4())
    await set_job_status(job_id, "queued")
    analyze_product_task.delay(job_id, payload.model_dump(), product_key)

    return SubmitResponse(cached=False, job_id=job_id, eta_seconds=12)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Poll job completion status. Called by extension every 2s after submit."""
    from cache import get_job_status
    job = await get_job_status(job_id)
    if not job:
        return {"status": "not_found"}
    return job