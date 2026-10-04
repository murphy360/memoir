"""xAI's Grok over its OpenAI-compatible chat completions API. The key travels in the
`Authorization` header.

Grok's chat API takes text, not audio, so it cannot transcribe: Memoir uses it for
extraction and questions. Structured answers use `response_format` with the schema.
"""

import json

import httpx

from app.ai import http
from app.ai.provider import Answer, Audio, ProviderError

BASE_URL = "https://api.x.ai/v1"


class Grok:
    name = "grok"
    audio = False
    inline_limit = 0

    def __init__(
        self,
        api_key: str,
        timeout: float,
        client: httpx.Client | None = None,
        base_url: str = BASE_URL,
    ):
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def _call(self, model: str, prompt: str, **extra) -> tuple[str, dict]:
        body = http.post(
            self._client,
            "Grok",
            f"{self._base}/chat/completions",
            {"Authorization": f"Bearer {self._key}"},
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                **extra,
            },
        )
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Grok gave no answer") from exc
        if message.get("refusal"):
            refusal = " ".join(str(message["refusal"]).split())[:200]
            raise ProviderError(f"Grok refused: {refusal}", retryable=False)
        return (message.get("content") or "").strip(), body

    @staticmethod
    def _answer(body: dict, model: str, text: str, data: dict | None = None):
        usage = body.get("usage") or {}
        return Answer(
            text=text,
            model=body.get("model") or model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            data=data or {},
        )

    def transcribe(self, audio: Audio, prompt: str, model: str) -> Answer:
        raise ProviderError("Grok cannot transcribe audio", retryable=False)

    def structured(self, prompt: str, schema: dict, model: str) -> Answer:
        shape = {"name": "answer", "schema": schema}
        text, body = self._call(
            model,
            prompt,
            temperature=0.1,
            response_format={"type": "json_schema", "json_schema": shape},
        )
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ProviderError("Grok's answer was not the JSON asked for") from exc
        if not isinstance(data, dict):
            raise ProviderError("Grok's answer was not the JSON asked for")
        return self._answer(body, model, text, data)

    def text(self, prompt: str, model: str) -> Answer:
        text, body = self._call(model, prompt, temperature=0.7)
        return self._answer(body, model, text)
