"""Signing in and out. Login, health and invitations are the routes open to all."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.accounts import audit, sessions
from app.accounts.deps import (
    Signed,
    client_ip,
    clear_session_cookies,
    set_session_cookies,
    signed_in_any,
)
from app.accounts.login import login
from app.accounts.schemas import LoginRequest, Me
from app.core.db import get_session
from app.core.errors import ErrorResponse
from app.core.settings import Settings, get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])
REFUSED = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}}


@router.post("/login", response_model=Me, responses=REFUSED)
def sign_in(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Me:
    user, row, token = login(
        db,
        body.email,
        body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        settings=settings,
    )
    set_session_cookies(response, token, row.csrf_token, settings)
    return Me.model_validate(user)


@router.post("/logout", status_code=204, responses=REFUSED)
def sign_out(
    response: Response,
    signed: Signed = Depends(signed_in_any),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> None:
    sessions.revoke(db, signed.session)
    clear_session_cookies(response, settings)


@router.post("/logout-all", status_code=204, responses=REFUSED)
def sign_out_everywhere_else(
    request: Request,
    signed: Signed = Depends(signed_in_any),
    db: Session = Depends(get_session),
) -> None:
    """Sign out every other browser; this one stays signed in."""
    count = sessions.revoke_all(db, signed.user.id, except_id=signed.session.id)
    audit.record(
        db,
        "logout.everywhere",
        archive_id=signed.user.archive_id,
        actor_id=signed.user.id,
        ip=client_ip(request),
        sessions=count,
    )
    db.commit()
