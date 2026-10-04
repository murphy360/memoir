"""OpenAI: chat completions for the text tasks, and the audio transcriptions endpoint,
so it can transcribe as well as Gemini. The key travels in the `Authorization` header.

Structured answers use `response_format` with the schema. GPT-5 models take only their
default temperature, so none is sent.
"""

import json

import httpx

from app.ai import http
from app.ai.provider import Answer, Audio, ProviderError

BASE_URL = "https://api.openai.com/v1"
# The transcriptions endpoint takes files up to 25 MB; segments stay well under, and
# about ten minutes long, so a transcription model's context is never the limit.
INLINE_LIMIT = 12 * 1024 * 1024
# It reads the format from the file name.
EXTENSIONS = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "video/mp4": "mp4",
    "audio/x-m4a": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


class OpenAI:
    name = "openai"
    audio = True
    inline_limit = INLINE_LIMIT

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

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._key}"}

    @staticmethod
    def _usage(body: dict) -> tuple[int, int]:
        usage = body.get("usage") or {}
        given = usage.get("prompt_tokens", usage.get("input_tokens", 0))
        made = usage.get("completion_tokens", usage.get("output_tokens", 0))
        return int(given or 0), int(made or 0)

    def _chat(self, model: str, prompt: str, **extra) -> tuple[str, dict]:
        body = http.post(
            self._client,
            "OpenAI",
            f"{self._base}/chat/completions",
            self._headers(),
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                **extra,
            },
        )
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("OpenAI gave no answer") from exc
        if message.get("refusal"):
            refusal = " ".join(str(message["refusal"]).split())[:200]
            raise ProviderError(f"OpenAI refused: {refusal}", retryable=False)
        return (message.get("content") or "").strip(), body

    def _answer(self, body: dict, model: str, text: str, data: dict | None = None):
        given, made = self._usage(body)
        return Answer(
            text=text,
            model=body.get("model") or model,
            input_tokens=given,
            output_tokens=made,
            data=data or {},
        )

    def transcribe(self, audio: Audio, prompt: str, model: str) -> Answer:
        kind = audio.mime_type.split(";")[0].strip().lower()
        name = f"recording.{EXTENSIONS.get(kind, 'webm')}"
        body = http.post(
            self._client,
            "OpenAI",
            f"{self._base}/audio/transcriptions",
            self._headers(),
            {"model": model, "prompt": prompt, "response_format": "json"},
            files={"file": (name, audio.data, kind)},
        )
        if not isinstance(body.get("text"), str):
            raise ProviderError("OpenAI gave no transcript")
        return self._answer(body, model, body["text"].strip())

    def structured(self, prompt: str, schema: dict, model: str) -> Answer:
        shape = {"name": "answer", "schema": schema, "strict": False}
        text, body = self._chat(
            model,
            prompt,
            response_format={"type": "json_schema", "json_schema": shape},
        )
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ProviderError("OpenAI's answer was not the JSON asked for") from exc
        if not isinstance(data, dict):
            raise ProviderError("OpenAI's answer was not the JSON asked for")
        return self._answer(body, model, text, data)

    def text(self, prompt: str, model: str) -> Answer:
        text, body = self._chat(model, prompt)
        return self._answer(body, model, text)
