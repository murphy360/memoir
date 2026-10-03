"""Google Gemini over its REST API. The key travels in a header, never in the URL."""

import base64
import json

import httpx

from app.ai.provider import Answer, Audio, ProviderError

BASE_URL = "https://generativelanguage.googleapis.com"
ENDPOINT = "{base}/v1beta/models/{model}:generateContent"
# Answers that waiting will not change: a bad request, a refused key, no credit, no
# model.
REFUSALS = {400, 401, 402, 403, 404}


def _reason(response: httpx.Response) -> str:
    """Gemini's own sentence for a refusal (never the key, which is only
    in a header).
    """
    try:
        message = response.json().get("error", {}).get("message", "")
    except ValueError:
        message = ""
    return " ".join(message.split())[:200] or response.reason_phrase


class Gemini:
    name = "gemini"
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
        try:
            response = self._client.post(
                ENDPOINT.format(base=self._base, model=model),
                headers={"x-goog-api-key": self._key},
                json={"contents": [{"parts": parts}], "generationConfig": config},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Gemini unreachable: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise ProviderError(
                f"Gemini answered {response.status_code}: {_reason(response)}",
                retryable=response.status_code not in REFUSALS,
            )
        body = response.json()
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
