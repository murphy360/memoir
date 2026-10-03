"""A provider for tests: scripted answers, every request recorded, no network."""

from collections.abc import Callable

from app.ai.provider import Answer, Audio, ProviderError


class FakeAI:
    name = "fake"

    def __init__(self, inline_limit: int = 50 * 1024 * 1024):
        self.inline_limit = inline_limit
        self.calls: list[dict] = []
        self.transcript: Callable[[Audio], str] | str = "A transcript."
        # A dict for every structured request, or a function of (prompt, schema).
        self.data: dict | Callable[[str, dict], dict] = {}
        self.reply = "A reply."
        self.fail_next = 0

    def _maybe_fail(self):
        if self.fail_next:
            self.fail_next -= 1
            raise ProviderError("the fake was told to fail")

    def transcribe(self, audio: Audio, prompt: str, model: str) -> Answer:
        self.calls.append(
            {"task": "transcribe", "bytes": len(audio.data), "mime": audio.mime_type}
        )
        self._maybe_fail()
        text = self.transcript(audio) if callable(self.transcript) else self.transcript
        return Answer(
            text=text,
            model=model,
            input_tokens=len(audio.data) // 1000,
            output_tokens=len(text),
        )

    def structured(self, prompt: str, schema: dict, model: str) -> Answer:
        self.calls.append({"task": "structured", "prompt": prompt, "schema": schema})
        self._maybe_fail()
        return Answer(
            text="{}",
            model=model,
            input_tokens=len(prompt),
            output_tokens=10,
            data=self.data(prompt, schema) if callable(self.data) else self.data,
        )

    def text(self, prompt: str, model: str) -> Answer:
        self.calls.append({"task": "text", "prompt": prompt})
        self._maybe_fail()
        return Answer(
            text=self.reply, model=model, input_tokens=len(prompt), output_tokens=5
        )
