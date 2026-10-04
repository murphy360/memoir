"""What Memoir asks of a text and audio AI provider, and what it gets back.

Prompts, parsing and limits live with the task that needs them (`app/analysis/`); a
provider only carries a request and reports what it cost.
"""

from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(Exception):
    """The provider failed. `retryable`: whether waiting and trying again may help (a
    network blip, a busy server) or not (no credit, a refused key, a bad request)."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class Audio:
    data: bytes
    mime_type: str


@dataclass
class Answer:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    data: dict = field(default_factory=dict)


class Provider(Protocol):
    name: str
    # Whether it hears audio: only a provider that does can transcribe.
    audio: bool
    # The largest audio one request may carry, in bytes, before it must be split.
    inline_limit: int

    def transcribe(self, audio: Audio, prompt: str, model: str) -> Answer: ...

    def structured(self, prompt: str, schema: dict, model: str) -> Answer:
        """Answer as JSON matching `schema`; the parsed object is in `Answer.data`."""
        ...

    def text(self, prompt: str, model: str) -> Answer: ...
