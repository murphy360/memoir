"""Server-side sessions: create, find, keep alive, revoke."""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.accounts.models import User, UserSession
from app.accounts.tokens import new_token, token_hash
from app.core.db import utcnow

# last_seen_at is written at most this often, so reading a page is not always a write.
TOUCH_EVERY = timedelta(minutes=1)


def start(session: Session, user: User, ip: str | None, user_agent: str | None):
    """Create a session; returns (the row, the raw token for the cookie). Commits."""
    token = new_token()
    row = UserSession(
        token_hash=token_hash(token),
        user_id=user.id,
        csrf_token=new_token(),
        ip=ip,
        user_agent=(user_agent or "")[:300] or None,
    )
    session.add(row)
    session.commit()
    return row, token


def find(session: Session, token: str, idle: timedelta) -> UserSession | None:
    """The live session for a cookie token; None if unknown, revoked or idle."""
    row = session.scalars(
        select(UserSession).where(UserSession.token_hash == token_hash(token))
    ).first()
    if row is None or row.revoked_at is not None:
        return None
    if utcnow() - row.last_seen_at > idle:
        return None
    return row


def touch(session: Session, row: UserSession) -> bool:
    """Record activity. True when the cookie's expiry should be pushed out too."""
    now = utcnow()
    if now - row.last_seen_at < TOUCH_EVERY:
        return False
    row.last_seen_at = now
    session.commit()
    return True


def revoke(session: Session, row: UserSession) -> None:
    row.revoked_at = utcnow()
    session.commit()


def revoke_all(session: Session, user_id: int, except_id: int | None = None) -> int:
    """Revoke every live session of a user (but one, if given). Returns how many."""
    stmt = update(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if except_id is not None:
        stmt = stmt.where(UserSession.id != except_id)
    count = session.execute(stmt.values(revoked_at=utcnow())).rowcount
    session.commit()
    return count
