"""Which provider does which task. Gemini, Anthropic, Grok and OpenAI each run when
their key is set; with no key at all, AI is off and nothing fails. Transcription needs
a provider that hears audio (Gemini or OpenAI): `MEMOIR_AI_TRANSCRIBE_PROVIDER`, else
the first of them with a key. Extraction and questions use the task's own setting or
`MEMOIR_AI_PROVIDER`, else the first provider with a key: Gemini, Anthropic, Grok,
OpenAI.

Tests put a fake in place of every provider with `use`.
"""

from app.ai.anthropic import Anthropic
from app.ai.gemini import Gemini
from app.ai.grok import Grok
from app.ai.openai import OpenAI
from app.ai.provider import Provider
from app.core.settings import Settings

MAKERS = {"gemini": Gemini, "anthropic": Anthropic, "grok": Grok, "openai": OpenAI}
ORDER = tuple(MAKERS)
HEARS = tuple(name for name, maker in MAKERS.items() if maker.audio)
TASKS = ("transcribe", "extract", "questions")
_override: Provider | None = None
_override_set = False


def use(provider: Provider | None) -> None:
    """Make `provider` the one Memoir uses for every task (tests); `reset()` undoes
    it."""
    global _override, _override_set
    _override, _override_set = provider, True


def reset() -> None:
    global _override, _override_set
    _override, _override_set = None, False


def _key(settings: Settings, name: str) -> str:
    secret = getattr(settings, f"{name}_api_key", None)
    return secret.get_secret_value() if secret is not None else ""


def configured(settings: Settings) -> list[str]:
    """The providers with a key, in order of preference."""
    return [name for name in ORDER if _key(settings, name)]


def build(settings: Settings, name: str) -> Provider:
    timeout = settings.ai_timeout_seconds
    return MAKERS[name](
        _key(settings, name), timeout, base_url=getattr(settings, f"{name}_base_url")
    )


def choose(settings: Settings, task: str) -> str | None:
    """The provider's name for a task, or None when no provider can do it."""
    if _override_set:
        return _override.name if _override is not None else None
    have = configured(settings)
    if task == "transcribe":
        have = [name for name in have if name in HEARS]
        wanted = settings.ai_transcribe_provider
    else:
        wanted = getattr(settings, f"ai_{task}_provider", "") or settings.ai_provider
    wanted = wanted.strip().lower()
    if wanted in have:
        return wanted
    return have[0] if have else None


def provider(settings: Settings, task: str = "extract") -> Provider | None:
    if _override_set:
        return _override
    name = choose(settings, task)
    return build(settings, name) if name else None


def model_for(settings: Settings, task: str, provider_name: str = "gemini") -> str:
    if provider_name == "openai" and task == "transcribe":
        return settings.openai_transcribe_model
    if provider_name in ("anthropic", "grok", "openai"):
        return getattr(settings, f"{provider_name}_model")
    specific = {
        "transcribe": settings.gemini_transcribe_model,
        "extract": settings.gemini_extract_model,
    }.get(task, "")
    return specific or settings.gemini_model
