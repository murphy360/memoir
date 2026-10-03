"""Which provider Memoir uses: Gemini when a key is set, none otherwise ("AI is off").
Tests put a fake in its place with `use`."""

from app.ai.gemini import Gemini
from app.ai.provider import Provider
from app.core.settings import Settings

_override: Provider | None = None
_override_set = False


def use(provider: Provider | None) -> None:
    """Make `provider` the one Memoir uses (tests); `reset()` undoes it."""
    global _override, _override_set
    _override, _override_set = provider, True


def reset() -> None:
    global _override, _override_set
    _override, _override_set = None, False


def provider(settings: Settings) -> Provider | None:
    if _override_set:
        return _override
    if (
        settings.gemini_api_key is None
        or not settings.gemini_api_key.get_secret_value()
    ):
        return None
    return Gemini(
        settings.gemini_api_key.get_secret_value(),
        settings.ai_timeout_seconds,
        base_url=settings.gemini_base_url,
    )


def model_for(settings: Settings, task: str) -> str:
    specific = {
        "transcribe": settings.gemini_transcribe_model,
        "extract": settings.gemini_extract_model,
    }.get(task, "")
    return specific or settings.gemini_model
