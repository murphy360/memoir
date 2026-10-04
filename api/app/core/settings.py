"""Every setting in one typed object, read from the environment once at startup."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEMOIR_", extra="ignore")

    database_url: str = "postgresql+psycopg://memoir:memoir@db:5432/memoir"
    blob_root: Path = Path("/data/blobs")
    log_level: str = "INFO"
    # Where the proxy mounts the API (the web app is at /memoir); used by the docs page.
    root_path: str = ""
    worker_poll_seconds: float = 2.0
    worker_heartbeat_seconds: float = 15.0
    # A running job whose heartbeat is older than this is stuck, and is claimed again.
    job_stale_seconds: float = 300.0
    # Retry n waits base * 2**(n-1) seconds, capped at an hour.
    job_backoff_base_seconds: float = 30.0
    # /api/health counts the worker alive while its heartbeat is younger than this.
    worker_alive_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
