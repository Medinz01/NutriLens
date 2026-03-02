import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from cache import get_cached_product, set_job_status, get_product_age_seconds
from models.schemas import ProductSubmitRequest, SubmitResponse, EnrichedProduct
from worker.celery_app import analyze_product_task
from config import get_settings

router = APIRouter()
settings = get_settings()


def make_product_id(platform: str, platform_id: str) -> str:
    return f"{platform}:{platform_id}"


@router.post("/products/submit", response_model=SubmitResponse)
async def submit_product(
    payload: ProductSubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the extension when user clicks '+ Compare'.

    Flow:
      1. Check Redis cache
      2. HIT  → return 200 with cached enriched data
      3. MISS → create job, enqueue to Celery, return 202 with job_id
      4. STALE (>30 days old) → return cached data BUT also enqueue refresh in background
    """
    platform    = payload.platform.replace("https://www.", "").replace("/", "")
    platform_id = payload.platform_id
    product_key = make_product_id(platform, platform_id)

    # ── Cache check ──────────────────────────────────────────────────────────
    cached = await get_cached_product(platform, platform_id)

    if cached:
        age = await get_product_age_seconds(platform, platform_id)
        is_stale = age and age > settings.stale_after_seconds

        if is_stale:
            # Serve stale data immediately, but kick off a background refresh
            job_id = str(uuid.uuid4())
            await set_job_status(job_id, "queued")
            analyze_product_task.delay(job_id, payload.model_dump(), product_key, refresh=True)

        return SubmitResponse(
            cached=True,
            data=EnrichedProduct(**cached),
        )

    # ── Cache miss: create async job ─────────────────────────────────────────
    job_id = str(uuid.uuid4())

    # Write job as "queued" to Redis immediately so polling works right away
    await set_job_status(job_id, "queued", error=None)

    # Enqueue the heavy ML work to Celery (non-blocking)
    analyze_product_task.delay(job_id, payload.model_dump(), product_key)

    return SubmitResponse(
        cached=False,
        job_id=job_id,
        eta_seconds=12,
    )