import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int = int(os.getenv("PORT", "8000"))
    host: str = os.getenv("HOST", "0.0.0.0")

    crossref_mailto: str = os.getenv("CROSSREF_MAILTO", "")
    semantic_scholar_api_key: str = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")

    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))
    cache_max_entries: int = int(os.getenv("CACHE_MAX_ENTRIES", "1000"))

    sqlite_path: str = os.getenv("SQLITE_PATH", "./data/papers.db")

    request_timeout: float = 5.0
    aggregate_timeout: float = 10.0

    arxiv_rate_per_sec: int = 1
    crossref_rate_per_sec: int = 5
    semantic_rate_per_min: int = 100

    class Config:
        env_file = ".env"


settings = Settings()
