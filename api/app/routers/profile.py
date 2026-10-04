"""The signed-in user's own account: who am I, my name, my password, my sessions."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.deps import Signed, signed_in_any
from app.accounts.login import change_password
from app.accounts.models import UserSession
from app.accounts.schemas import ChangePassword, Me, SessionInfo, UpdateMe
from app.core.db import get_session, utcnow
from app.core.errors import ErrorResponse

router = APIRouter(prefix="/api/me", tags=["profile"])
REFUSED = {401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}


@router.get("", response_model=Me, responses=REFUSED)
def me(signed: Signed = Depends(signed_in_any)) -> Me:
    return Me.model_validate(signed.user)


@router.patch("", response_model=Me, responses=REFUSED)
def update_me(
    body: UpdateMe,
    signed: Signed = Depends(signed_in_any),
    db: Session = Depends(get_session),
) -> Me:
    signed.user.display_name = body.display_name.strip()
    db.commit()
    return Me.model_validate(signed.user)


@router.post("/password", status_code=204, responses=REFUSED)
def new_password(
    body: ChangePassword,
    signed: Signed = Depends(signed_in_any),
    db: Session = Depends(get_session),
) -> None:
    change_password(
        db, signed.user, body.current_password, body.new_password, signed.session.id
    )


@router.get("/sessions", response_model=list[SessionInfo], responses=REFUSED)
def my_sessions(
    signed: Signed = Depends(signed_in_any), db: Session = Depends(get_session)
) -> list[SessionInfo]:
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == signed.user.id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_seen_at.desc())
    )
    now = utcnow()
    return [
        SessionInfo(
            id=r.id,
            created_at=r.created_at,
            last_seen_at=min(r.last_seen_at, now),
            user_agent=r.user_agent,
            ip=r.ip,
            current=r.id == signed.session.id,
        )
        for r in rows
    ]
