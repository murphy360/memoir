"""FastAPI dependencies: who is signed in, and may they do this?

Every router uses one of these. `require_role(Role.CONTRIBUTOR)` admits contributors and
owners; `require_executor` admits the executor grant (and owners). A user whose password
must be changed is admitted only to the routes that let them change it.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.accounts import sessions
from app.accounts.csrf import CSRF_HEADER, UNSAFE
from app.accounts.models import Role, User, UserSession
from app.core.audited import act_as
from app.core.db import get_session
from app.core.errors import ApiError
from app.core.settings import Settings, get_settings

SESSION_COOKIE = "memoir_session"


@dataclass
class Signed:
    """The request's user and session."""

    user: User
    session: UserSession


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def set_session_cookies(
    response: Response, token: str, csrf: str, settings: Settings
) -> None:
    age = int(timedelta(days=settings.session_idle_days).total_seconds())
    common = {
        "max_age": age,
        "path": settings.cookie_path,
        "secure": settings.cookie_secure,
        "samesite": "lax",
    }
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **common)
    # Readable by the web app, which echoes it in the X-CSRF-Token header.
    response.set_cookie("memoir_csrf", csrf, httponly=False, **common)


def clear_session_cookies(response: Response, settings: Settings) -> None:
    for name in (SESSION_COOKIE, "memoir_csrf"):
        response.delete_cookie(name, path=settings.cookie_path)


def _unauthenticated() -> ApiError:
    return ApiError(401, "unauthenticated", "Please sign in.")


def signed_in_any(
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Signed:
    """A signed-in user, even one who must change their password first."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _unauthenticated()
    idle = timedelta(days=settings.session_idle_days)
    row = sessions.find(db, token, idle)
    user = db.get(User, row.user_id) if row else None
    if row is None or user is None or user.deleted_at is not None:
        raise _unauthenticated()
    sent = request.headers.get(CSRF_HEADER, "")
    if request.method in UNSAFE and not secrets.compare_digest(sent, row.csrf_token):
        raise ApiError(403, "csrf_failed", "This request did not come from Memoir.")
    if sessions.touch(db, row):
        set_session_cookies(response, token, row.csrf_token, settings)
    act_as(db, user.id)
    return Signed(user, row)


def signed_in(signed: Signed = Depends(signed_in_any)) -> Signed:
    """A signed-in user who may use the app (no password change pending)."""
    if signed.user.must_change_password:
        raise ApiError(
            403,
            "password_change_required",
            "Choose a new password before you continue.",
        )
    return signed


def require_role(role: Role) -> Callable[..., User]:
    def check(signed: Signed = Depends(signed_in)) -> User:
        if not signed.user.at_least(role):
            raise ApiError(403, "forbidden", "Your role does not allow this.")
        return signed.user

    check.__name__ = f"require_{role.value}"
    return check


def require_executor(signed: Signed = Depends(signed_in)) -> User:
    if not (signed.user.is_executor or signed.user.at_least(Role.OWNER)):
        raise ApiError(403, "forbidden", "Only the executor or an owner may do this.")
    return signed.user
