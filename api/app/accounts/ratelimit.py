"""Login rate limits in Postgres: per address and per account, over a time window."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.models import LoginAttempt
from app.core.db import utcnow
from app.core.settings import Settings


def _failures(session: Session, column, value: str, window: int) -> int:
    since = utcnow() - timedelta(seconds=window)
    return session.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(column == value, LoginAttempt.created_at >= since)
        .where(LoginAttempt.succeeded.is_(False))
    )


def blocked(session: Session, ip: str, email: str, settings: Settings) -> bool:
    """True when this address or this account has failed too often recently."""
    by_ip = _failures(session, LoginAttempt.ip, ip, settings.login_ip_window_seconds)
    if by_ip >= settings.login_ip_limit:
        return True
    by_account = _failures(
        session, LoginAttempt.email, email, settings.login_account_window_seconds
    )
    return by_account >= settings.login_account_limit


def note(session: Session, ip: str, email: str, succeeded: bool) -> None:
    session.add(LoginAttempt(ip=ip, email=email, succeeded=succeeded))
