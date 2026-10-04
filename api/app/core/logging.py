"""Structured logs: one JSON object per line, with the request or job id it belongs to.

Logs hold ids, durations and error classes; never transcripts, file contents or keys.
"""

import json
import logging
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

context_id: ContextVar[str | None] = ContextVar("context_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "context": context_id.get(),
        }
        if record.exc_info:
            entry["error"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(entry)


def configure(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    # Alembic announces every plugin it loads at INFO; only its warnings are news.
    logging.getLogger("alembic").setLevel(logging.WARNING)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Takes X-Request-ID from the proxy or makes one, and echoes it on the response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = context_id.set(f"req:{rid}")
        try:
            response = await call_next(request)
        finally:
            context_id.reset(token)
        response.headers["x-request-id"] = rid
        return response
