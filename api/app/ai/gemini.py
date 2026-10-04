"""Google Gemini over its REST API. The key travels in a header, never in the URL."""

import base64
import json

import httpx

from app.ai import http
from app.ai.provider import Answer, Audio, ProviderError

BASE_URL = "https://generativelanguage.googleapis.com"
ENDPOINT = "{base}/v1beta/models/{model}:generateContent"


class Gemini:
    name = "gemini"
    # Gemini hears audio, so it can transcribe.
    audio = True
    # Gemini takes 20 MB per request; base64 grows audio by a third, so stay well under.
    inline_limit = 12 * 1024 * 1024

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

    def _call(self, model: str, parts: list[dict], config: dict) -> tuple[str, dict]:
        body = http.post(
            self._client,
            "Gemini",
            ENDPOINT.format(base=self._base, model=model),
            {"x-goog-api-key": self._key},
            {"contents": [{"parts": parts}], "generationConfig": config},
        )
        try:
            texts = [
                p.get("text", "") for p in body["candidates"][0]["content"]["parts"]
            ]
        except (KeyError, IndexError, TypeError) as exc:
            reason = body.get("promptFeedback", {}).get("blockReason", "no answer")
            raise ProviderError(f"Gemini gave no answer ({reason})") from exc
        return "".join(texts).strip(), body.get("usageMetadata", {})

    @staticmethod
    def _answer(text: str, usage: dict, model: str, data: dict | None = None) -> Answer:
        return Answer(
            text=text,
            model=model,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            data=data or {},
        )

    def transcribe(self, audio: Audio, prompt: str, model: str) -> Answer:
        inline = {
            "inline_data": {
                "mime_type": audio.mime_type,
                "data": base64.b64encode(audio.data).decode(),
            }
        }
        text, usage = self._call(model, [{"text": prompt}, inline], {"temperature": 0})
        return self._answer(text, usage, model)

    def structured(self, prompt: str, schema: dict, model: str) -> Answer:
        config = {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        }
        text, usage = self._call(model, [{"text": prompt}], config)
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ProviderError("Gemini's answer was not the JSON asked for") from exc
        return self._answer(text, usage, model, data)

    def text(self, prompt: str, model: str) -> Answer:
        text, usage = self._call(model, [{"text": prompt}], {"temperature": 0.7})
        return self._answer(text, usage, model)
