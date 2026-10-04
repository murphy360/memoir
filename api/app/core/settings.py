"""Every setting in one typed object, read from the environment once at startup."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
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

    # Accounts. The app's own address, for invitation links (ends with the base path).
    public_url: str = "http://localhost:8080/memoir/"
    # Origins allowed to send state-changing requests (comma-separated): the CSRF check.
    allowed_origins: str = "http://localhost:8080,http://localhost:5173"
    # Off only for local development over plain http.
    cookie_secure: bool = True
    cookie_path: str = "/"
    session_idle_days: int = 30
    invitation_days: int = 7
    # Failed logins allowed in a window before every attempt is refused for a while.
    login_ip_limit: int = 5
    login_ip_window_seconds: int = 60
    login_account_limit: int = 10
    login_account_window_seconds: int = 900
    # The proxies whose X-Forwarded-For uvicorn believes ("*" behind Caddy or nginx).
    forwarded_allow_ips: str = "127.0.0.1"

    # Text and audio AI (requirements 6.1). No key: AI is off, and nothing fails.
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    # Where Gemini is reached; a stand-in for end-to-end runs may take its place.
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    # Per task, when one task deserves another model; empty means gemini_model.
    gemini_transcribe_model: str = ""
    gemini_extract_model: str = ""
    # Anthropic's Claude and xAI's Grok read text only: extraction and questions, never
    # transcription.
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5"
    anthropic_base_url: str = "https://api.anthropic.com"
    grok_api_key: SecretStr | None = None
    grok_model: str = "grok-4.7"
    grok_base_url: str = "https://api.x.ai/v1"
    # OpenAI reads text and also transcribes.
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.5"
    openai_transcribe_model: str = "gpt-transcribe"
    openai_base_url: str = "https://api.openai.com/v1"
    # Which provider does the text tasks (gemini, anthropic, grok or openai); empty
    # means the first with a key, in that order. A task may name its own.
    ai_provider: str = ""
    # Which provider transcribes (gemini or openai); empty means the first with a key.
    ai_transcribe_provider: str = ""
    ai_extract_provider: str = ""
    ai_questions_provider: str = ""
    ai_timeout_seconds: float = 180.0

    @property
    def origins(self) -> set[str]:
        return {o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o}


@lru_cache
def get_settings() -> Settings:
    return Settings()
