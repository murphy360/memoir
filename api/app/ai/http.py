"""What every HTTP provider shares: one POST, and the provider's own reason when it
refuses, marked retryable or not."""

import httpx

from app.ai.provider import ProviderError

# Answers that waiting will not change: a bad request, a refused key, no credit, no
# model, a request too large.
REFUSALS = {400, 401, 402, 403, 404, 413, 422}


def reason(response: httpx.Response) -> str:
    """The provider's own sentence for a refusal. Keys travel only in headers, so it
    never carries one."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error", "") if isinstance(body, dict) else ""
    message = error.get("message", "") if isinstance(error, dict) else str(error)
    return " ".join(message.split())[:200] or response.reason_phrase


def post(client: httpx.Client, who: str, url: str, headers: dict, body: dict) -> dict:
    """POST JSON and return the JSON answer, or raise ProviderError saying why."""
    try:
        response = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise ProviderError(f"{who} unreachable: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise ProviderError(
            f"{who} answered {response.status_code}: {reason(response)}",
            retryable=response.status_code not in REFUSALS,
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError(f"{who}'s answer was not JSON") from exc
