"""Anthropic's Claude over the Messages API. The key travels in the `x-api-key`
header.

Claude reads text, not audio, so it cannot transcribe: Memoir uses it for extraction
and questions. A structured answer is asked for as one forced tool call whose input
schema is the schema wanted, so the answer arrives already parsed.
"""

import json

import httpx

from app.ai import http
from app.ai.provider import Answer, Audio, ProviderError

BASE_URL = "https://api.anthropic.com"
VERSION = "2023-06-01"
MAX_TOKENS = 4096


def unpack(data: dict, schema: dict) -> dict:
    """Undo a habit of Claude's tool calls: a list or object field sent as a JSON
    string, sometimes the whole answer inside its own field. Each such field is decoded
    against the schema; anything else is kept as it came."""
    wanted = {"array": list, "object": dict}
    out = dict(data)
    for key, spec in (schema.get("properties") or {}).items():
        kind = wanted.get(spec.get("type"))
        value = out.get(key)
        if kind is None or not isinstance(value, str):
            continue
        try:
            decoded = json.loads(value)
        except ValueError:
            continue
        if isinstance(decoded, dict) and kind is list and key in decoded:
            decoded = decoded[key]
        if isinstance(decoded, kind):
            out[key] = decoded
    return out


class Anthropic:
    name = "anthropic"
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

    def _call(self, model: str, prompt: str, **extra) -> dict:
        return http.post(
            self._client,
            "Anthropic",
            f"{self._base}/v1/messages",
            {"x-api-key": self._key, "anthropic-version": VERSION},
            {
                "model": model,
                "max_tokens": MAX_TOKENS,
                "messages": [{"role": "user", "content": prompt}],
                **extra,
            },
        )

    @staticmethod
    def _answer(body: dict, model: str, text: str, data: dict | None = None):
        usage = body.get("usage") or {}
        return Answer(
            text=text,
            model=body.get("model") or model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            data=data or {},
        )

    def transcribe(self, audio: Audio, prompt: str, model: str) -> Answer:
        raise ProviderError("Anthropic cannot transcribe audio", retryable=False)

    def structured(self, prompt: str, schema: dict, model: str) -> Answer:
        tool = {
            "name": "answer",
            "description": "Record the answer in this shape.",
            "input_schema": schema,
        }
        body = self._call(
            model,
            prompt,
            tools=[tool],
            tool_choice={"type": "tool", "name": "answer"},
        )
        for block in body.get("content") or []:
            if block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
                data = unpack(block["input"], schema)
                return self._answer(body, model, "", data)
        reason = body.get("stop_reason") or "no answer"
        raise ProviderError(f"Anthropic gave no answer ({reason})")

    def text(self, prompt: str, model: str) -> Answer:
        body = self._call(model, prompt)
        parts = [
            b.get("text", "")
            for b in body.get("content") or []
            if b.get("type") == "text"
        ]
        return self._answer(body, model, "".join(parts).strip())
