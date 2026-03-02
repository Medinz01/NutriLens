import json
import redis.asyncio as aioredis
from config import get_settings

settings = get_settings()

_redis_client = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


def _product_key(platform: str, platform_id: str) -> str:
    return f"product:{platform}:{platform_id}"

def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


async def get_cached_product(platform: str, platform_id: str) -> dict | None:
    r = await get_redis()
    raw = await r.get(_product_key(platform, platform_id))
    return json.loads(raw) if raw else None


async def set_cached_product(platform: str, platform_id: str, data: dict, ttl: int = None):
    r = await get_redis()
    ttl = ttl or settings.cache_ttl_seconds
    await r.setex(
        _product_key(platform, platform_id),
        ttl,
        json.dumps(data)
    )


async def get_product_age_seconds(platform: str, platform_id: str) -> int | None:
    """Returns how many seconds ago the product was cached, or None if not cached."""
    r = await get_redis()
    key = _product_key(platform, platform_id)
    ttl = await r.ttl(key)
    if ttl < 0:
        return None
    return settings.cache_ttl_seconds - ttl


async def set_job_status(job_id: str, status: str, data: dict = None, error: str = None):
    r = await get_redis()
    payload = {"status": status}
    if data:
        payload["data"] = data
    if error:
        payload["error"] = error
    # Jobs expire after 24h — no need to keep them longer
    await r.setex(_job_key(job_id), 86400, json.dumps(payload))


async def get_job_status(job_id: str) -> dict | None:
    r = await get_redis()
    raw = await r.get(_job_key(job_id))
    return json.loads(raw) if raw else None
