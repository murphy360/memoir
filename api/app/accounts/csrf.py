"""CSRF protection: a same-site cookie, an Origin check, and a per-session token.

Every state-changing request must come from one of the allowed origins (the Origin
header, or the Referer when a browser leaves Origin out). A signed-in request must also
carry the session's CSRF token in the X-CSRF-Token header (checked in deps.py).
"""

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.settings import get_settings

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_COOKIE = "memoir_csrf"
CSRF_HEADER = "x-csrf-token"


def origin_of(request: Request) -> str | None:
    origin = request.headers.get("origin")
    if origin and origin != "null":
        return origin.rstrip("/")
    referer = request.headers.get("referer")
    if referer:
        parts = urlsplit(referer)
        return f"{parts.scheme}://{parts.netloc}"
    return None


def refused() -> JSONResponse:
    body = {
        "error": {
            "code": "csrf_failed",
            "message": "This request did not come from Memoir.",
            "field": None,
        }
    }
    return JSONResponse(body, 403)


class OriginCheckMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if (
            request.method in UNSAFE
            and origin_of(request) not in get_settings().origins
        ):
            return refused()
        return await call_next(request)
