from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url:      str = "postgresql+asyncpg://nutrilens:nutrilens_dev@localhost:5432/nutrilens"
    sync_database_url: str = "postgresql+psycopg2://nutrilens:nutrilens_dev@localhost:5432/nutrilens"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery (separate Redis DBs to avoid key collisions)
    celery_broker_url:    str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # LLM — Phase 7
    # Get a free key at https://console.groq.com
    # Leave empty to run rule-based only (graceful fallback)
    groq_api_key: str = ""

    # App
    env:                  str = "development"
    cache_ttl_seconds:    int = 60 * 60 * 24 * 60   # 60 days
    stale_after_seconds:  int = 60 * 60 * 24 * 30   # 30 days → background refresh

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()