"""
worker/celery_app.py

Celery setup + the core analysis task.

Right now the pipeline is a placeholder that:
  1. Normalizes nutrition data
  2. Runs the rule-based contradiction engine (no ML yet)
  3. Computes a basic score
  4. Writes to Postgres + Redis cache

Phase 4 will slot in the spaCy NER and BERT classifier here.
"""

import sys
import os

# Ensure /app is on the path for forked worker subprocesses
sys.path.insert(0, "/app")

import uuid
import json
import logging
from celery import Celery
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "nutrilens",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


@celery_app.task(bind=True, name="analyze_product", max_retries=2)
def analyze_product_task(self, job_id: str, raw_payload: dict, product_key: str, refresh: bool = False):
    """
    Main ML pipeline task. Runs synchronously inside Celery worker.

    Stages:
      1. Normalize nutrition facts to per-100g and per-₹100
      2. Detect category (protein_powder, health_bar, etc.)
      3. Run contradiction engine (rule-based)
      4. [Phase 4] Claim extraction + classification (spaCy + BERT)
      5. Compute NutriScore
      6. Persist to Postgres
      7. Write to Redis cache
      8. Update job status
    """
    import redis as sync_redis
    from sqlalchemy.orm import Session
    from database import sync_engine
    from engines.contradiction import run_contradiction_engine
    from engines.ranker import compute_score
    from engines.normalizer import normalize_nutrition
    from engines.ocr import process_product_images

    r = sync_redis.from_url(settings.redis_url, decode_responses=True)
    job_key = f"job:{job_id}"

    def update_job(status, data=None, error=None, eta=None):
        payload = {"status": status}
        if data:   payload["data"] = data
        if error:  payload["error"] = error
        if eta:    payload["eta_seconds"] = eta
        r.setex(job_key, 86400, json.dumps(payload))

    try:
        update_job("processing", eta=8)

        platform    = raw_payload.get("platform", "").replace("https://www.", "").replace("/", "")
        platform_id = raw_payload.get("platform_id", "")

        # ── DEBUG ─────────────────────────────────────────────────────────
        ocr_urls_debug = raw_payload.get("ocr_target_urls")
        logger.info(f"[worker] ocr_target_urls received: {ocr_urls_debug}")
        logger.info(f"[worker] nutrition_facts received: {raw_payload.get('nutrition_facts')}")
        # ── END DEBUG ─────────────────────────────────────────────────────

        # ── 1. Normalize nutrition ────────────────────────────────────────
        normalized = normalize_nutrition(raw_payload)

        # ── 2. OCR Pipeline ───────────────────────────────────────────────
        ocr_target_urls = raw_payload.get("ocr_target_urls") or []
        dom_nutrition   = raw_payload.get("nutrition_facts") or {}
        dom_serving     = raw_payload.get("serving_size_g")

        ocr_result = {}
        if ocr_target_urls:
            logger.info(f"[worker] Running OCR on {len(ocr_target_urls)} images")
            ocr_result = process_product_images(
                ocr_target_urls=ocr_target_urls,
                dom_nutrition=dom_nutrition,
                dom_serving_size=dom_serving,
            )

            # If OCR found better nutrition, re-normalize with merged data
            if ocr_result.get("ocr_success") and ocr_result.get("merged_nutrition"):
                merged_payload = {**raw_payload}
                merged_payload["nutrition_facts"] = ocr_result["merged_nutrition"]
                merged_payload["nutrition_unit"]   = "per_100g"  # OCR returns per-100g

                # Use OCR serving size if DOM didn't have one
                if not dom_serving and ocr_result.get("ocr_serving_size"):
                    merged_payload["serving_size_g"] = ocr_result["ocr_serving_size"]

                # Use OCR ingredients if DOM didn't have them
                if not raw_payload.get("ingredients_text") and ocr_result.get("ocr_ingredients"):
                    merged_payload["ingredients_text"] = ocr_result["ocr_ingredients"]

                normalized = normalize_nutrition(merged_payload)

        # ── 3. Category detection ─────────────────────────────────────────
        category = detect_category(raw_payload.get("product_name", ""),
                                   raw_payload.get("claims_text", ""))

        # ── 4. Contradiction engine ────────────────────────────────────────
        claims_text  = raw_payload.get("claims_text", "")
        nutrition    = normalized.get("per_100g", {})
        contradictions, vague_claims = run_contradiction_engine(claims_text, nutrition)

        # ── 5. Score ──────────────────────────────────────────────────────
        scores = compute_score(
            nutrition_per_100g=normalized.get("per_100g", {}),
            nutrition_per_rs100=normalized.get("per_rs100", {}),
            contradictions=contradictions,
            vague_claims=vague_claims,
            category=category,
            fssai=raw_payload.get("fssai"),
            claims=raw_payload.get("claims", []),
            serving_size_g=raw_payload.get("serving_size_g"),
        )

        # ── 6. Build enriched product ──────────────────────────────────────
        enriched = {
            "platform_id":   platform_id,
            "platform":      platform,
            "url":           raw_payload.get("url", ""),
            "product_name":  raw_payload.get("product_name"),
            "brand":         raw_payload.get("brand"),
            "price_inr":     raw_payload.get("price_inr"),
            "quantity_g":    raw_payload.get("quantity_g"),
            "price_per_100g": normalized.get("price_per_100g"),
            "serving_size_g": raw_payload.get("serving_size_g"),
            "nutrition_per_100g":  normalized.get("per_100g"),
            "nutrition_per_rs100": normalized.get("per_rs100"),
            "nutrition_confidence": ocr_result.get("confidence") or raw_payload.get("nutrition_confidence"),
            "extraction_method":    "ocr" if ocr_result.get("ocr_success") else raw_payload.get("extraction_method"),
            "fssai_number":         ocr_result.get("fssai_number"),
            "ocr_conflicts":        ocr_result.get("conflicts", []),
            "analysis": {
                "factual_claims":   [],
                "certified_claims": [],
                "vague_claims":     [{"claim": c["claim"], "type": "VAGUE", "reason": c["reason"]}
                                     for c in vague_claims],
                "contradictions":   [{"claim": c["claim"], "explanation": c["explanation"],
                                      "severity": c["severity"], "citation": c.get("citation")}
                                     for c in contradictions],
            },
            "scores": {
                "value_score":     scores.get("value_score"),
                "quality_score":   scores.get("quality_score"),
                "integrity_score": scores.get("integrity_score"),
                "total":           scores.get("total"),
                "category":        scores.get("category"),
                "integrity_notes": scores.get("integrity_notes", []),
            },
            "claim_check": scores.get("claim_check", {}),
            "status": "ready",
        }

        # ── 6. Persist to Postgres ─────────────────────────────────────────
        with Session(sync_engine) as session:
            _upsert_product(session, raw_payload, normalized, contradictions, vague_claims, scores)

        # ── 7. Write to Redis cache ────────────────────────────────────────
        cache_key = f"product:{platform}:{platform_id}"
        r.setex(cache_key, settings.cache_ttl_seconds, json.dumps(enriched))

        # ── 8. Mark job complete ───────────────────────────────────────────
        update_job("complete", data=enriched)
        logger.info(f"[worker] Job {job_id} complete for {product_key}")

    except Exception as exc:
        logger.exception(f"[worker] Job {job_id} failed: {exc}")
        update_job("failed", error=str(exc))
        raise self.retry(exc=exc, countdown=5)


# ─── Category detection (simple keyword heuristic for now) ──────────────────

CATEGORY_KEYWORDS = {
    "protein_powder":  ["whey", "protein powder", "casein", "isolate", "mass gainer", "creapure", "creatine"],
    "health_bar":      ["protein bar", "energy bar", "granola bar", "nutrition bar"],
    "breakfast_cereal":["oats", "muesli", "cornflakes", "cereal", "porridge"],
}

def detect_category(product_name: str, claims_text: str) -> str:
    combined = (product_name + " " + claims_text).lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return category
    return "general"


# ─── Postgres upsert ──────────────────────────────────────────────────────────

def _upsert_product(session, raw, normalized, contradictions, vague_claims, scores):
    from models.db_models import Product, NutritionFacts, Contradiction, ExtractedClaim, ProductScore
    from datetime import datetime, timezone

    platform    = raw.get("platform", "").replace("https://www.", "").replace("/", "")
    platform_id = raw.get("platform_id", "")
    product_id  = f"{platform}:{platform_id}"
    now         = datetime.now(timezone.utc)

    # Upsert product row
    product = session.get(Product, product_id)
    if not product:
        product = Product(id=product_id, platform_id=platform_id, platform_name=platform)
        session.add(product)

    product.product_name      = raw.get("product_name")
    product.brand             = raw.get("brand")
    product.url               = raw.get("url")
    product.primary_image_url = raw.get("primary_image_url")
    product.last_extracted_at = now

    # Upsert nutrition facts
    per100g  = normalized.get("per_100g", {}) or {}
    per_rs   = normalized.get("per_rs100", {}) or {}

    if product.nutrition_facts:
        nf = product.nutrition_facts
    else:
        nf = NutritionFacts(product_id=product_id)
        session.add(nf)

    nf.price_inr         = raw.get("price_inr")
    nf.quantity_g        = raw.get("quantity_g")
    nf.price_per_100g    = normalized.get("price_per_100g")
    nf.serving_size_g    = raw.get("serving_size_g")
    nf.energy_kcal       = per100g.get("energy_kcal")
    nf.protein_g         = per100g.get("protein_g")
    nf.total_fat_g       = per100g.get("total_fat_g")
    nf.saturated_fat_g   = per100g.get("saturated_fat_g")
    nf.carbohydrates_g   = per100g.get("carbohydrates_g")
    nf.sugar_g           = per100g.get("sugar_g")
    nf.dietary_fiber_g   = per100g.get("dietary_fiber_g")
    nf.sodium_mg         = per100g.get("sodium_mg")
    nf.protein_per_rs100 = per_rs.get("protein_g")
    nf.energy_per_rs100  = per_rs.get("energy_kcal")
    nf.confidence        = 0.7 if raw.get("nutrition_confidence") == "high" else 0.4

    # Delete old contradictions and re-insert fresh ones
    for c in list(product.contradictions):
        session.delete(c)
    for c in contradictions:
        session.add(Contradiction(
            product_id=product_id,
            claim_text=c["claim"],
            severity=c["severity"],
            explanation=c["explanation"],
            citation_url=c.get("citation"),
        ))

    # Upsert scores
    if product.scores:
        sc = product.scores
    else:
        sc = ProductScore(product_id=product_id)
        session.add(sc)

    sc.value_score     = scores.get("value_score")
    sc.quality_score   = scores.get("quality_score")
    sc.integrity_score = scores.get("integrity_score")
    sc.total           = scores.get("total")
    sc.category        = scores.get("category")
    sc.computed_at     = now

    # Save claim verification results
    from models.db_models import ClaimVerification
    # Clear old verifications for this product
    session.query(ClaimVerification).filter(
        ClaimVerification.product_id == product_id
    ).delete()

    claim_check = scores.get("claim_check", {})
    for verdict, items in [
        ("verified",     claim_check.get("verified", [])),
        ("contradicted", claim_check.get("contradicted", [])),
        ("unverifiable", claim_check.get("unverifiable", [])),
    ]:
        for item in items:
            session.add(ClaimVerification(
                product_id  = product_id,
                claim_text  = item.get("claim", "")[:500],
                nutrient    = item.get("nutrient"),
                claimed_val = item.get("claimed"),
                actual_val  = item.get("actual"),
                unit        = item.get("unit"),
                verdict     = verdict,
                explanation = item.get("explanation"),
            ))

    session.commit()