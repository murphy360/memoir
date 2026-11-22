"""Signing in and changing passwords."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts import audit, ratelimit, sessions
from app.accounts.models import User, UserSession
from app.accounts.passwords import (
    DUMMY_HASH,
    check_rules,
    hash_password,
    verify_password,
)
from app.agents import grants
from app.core.errors import ApiError
from app.core.settings import Settings

GENERIC = "That email and password do not match an account."


def find_user(session: Session, email: str) -> User | None:
    return session.scalars(
        select(User).where(
            func.lower(User.email) == email.strip().lower(), User.deleted_at.is_(None)
        )
    ).first()


def check_password(
    session: Session,
    email: str,
    password: str,
    *,
    ip: str,
    settings: Settings,
    kind: str = "login.succeeded",
    **detail,
) -> User:
    """The account these match, after the rate limits; a 401 otherwise.

    Every refusal looks the same, so an attacker learns nothing from it. Signing in to
    the app and connecting an agent both come through here, under the same limits.
    """
    email_key = email.strip().lower()
    user = find_user(session, email_key)
    if ratelimit.blocked(session, ip, email_key, settings):
        verify_password(DUMMY_HASH, password)
        _refuse(session, email_key, ip, user, "login.blocked")
    if user is None or not verify_password(user.password_hash, password):
        if user is None:
            verify_password(DUMMY_HASH, password)
        _refuse(session, email_key, ip, user, "login.failed")
    ratelimit.note(session, ip, email_key, True)
    audit.record(
        session, kind, archive_id=user.archive_id, actor_id=user.id, ip=ip, **detail
    )
    return user


def login(
    session: Session,
    email: str,
    password: str,
    *,
    ip: str,
    user_agent: str | None,
    settings: Settings,
) -> tuple[User, UserSession, str]:
    """Check the password and the rate limits, then start a session."""
    user = check_password(session, email, password, ip=ip, settings=settings)
    row, token = sessions.start(session, user, ip, user_agent)
    return user, row, token


def _refuse(session: Session, email: str, ip: str, user: User | None, kind: str):
    ratelimit.note(session, ip, email, False)
    audit.record(
        session,
        kind,
        archive_id=user.archive_id if user else None,
        subject_user_id=user.id if user else None,
        ip=ip,
        email=email,
    )
    session.commit()
    raise ApiError(401, "login_failed", GENERIC)


def change_password(
    session: Session, user: User, current: str, new: str, keep_session_id: int
) -> None:
    """The user's own change. Every other session of theirs is signed out."""
    if not verify_password(user.password_hash, current):
        raise ApiError(
            422,
            "wrong_password",
            "Your current password is not right.",
            "current_password",
        )
    check_rules(new, user.email)
    user.password_hash = hash_password(new)
    user.must_change_password = False
    audit.record(
        session,
        "password.changed",
        archive_id=user.archive_id,
        actor_id=user.id,
        subject_user_id=user.id,
    )
    session.commit()
    sessions.revoke_all(session, user.id, except_id=keep_session_id)
    grants.end_all(session, user.id)
