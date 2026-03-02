from fastapi import APIRouter, HTTPException
from cache import get_redis
from models.schemas import RankRequest, RankResponse, RankedProduct
import json

router = APIRouter()


@router.post("/products/rank", response_model=RankResponse)
async def rank_products(body: RankRequest):
    """
    Given a list of platform_ids, fetch their cached enriched data
    and return them ranked by total NutriScore.
    """
    r = await get_redis()
    scored = []

    for pid in body.platform_ids:
        # platform_ids from extension are in format "platform:id"
        parts = pid.split(":", 1)
        if len(parts) != 2:
            continue
        platform, platform_id = parts
        key = f"product:{platform}:{platform_id}"
        raw = await r.get(key)
        if not raw:
            continue

        data = json.loads(raw)
        score = data.get("scores", {})
        total = score.get("total") if score else None

        scored.append({
            "platform_id":  pid,
            "product_name": data.get("product_name"),
            "score":        total or 0.0,
        })

    if not scored:
        raise HTTPException(status_code=404, detail="No analysed products found for given IDs")

    ranked = sorted(scored, key=lambda x: x["score"], reverse=True)

    return RankResponse(
        ranked=[
            RankedProduct(
                platform_id=p["platform_id"],
                rank=i + 1,
                score=p["score"],
                product_name=p["product_name"],
            )
            for i, p in enumerate(ranked)
        ]
    )