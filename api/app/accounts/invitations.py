"""Invitations: the only way in after the owner. Single use, and gone after a week."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts import audit, sessions
from app.accounts.login import find_user
from app.accounts.models import Invitation, User
from app.accounts.passwords import check_rules, hash_password
from app.accounts.tokens import new_token, token_hash
from app.archive.models import Archive
from app.core.db import utcnow
from app.core.errors import ApiError
from app.core.settings import Settings

GONE = "This invitation has expired or was already used. Ask for a new one."


def create(
    session: Session, owner: User, email: str, role: str, executor: bool, s: Settings
) -> tuple[Invitation, str]:
    """Make an invitation; returns it and the link (shown once)."""
    if find_user(session, email):
        raise ApiError(
            409, "already_a_user", "Someone already uses that email.", "email"
        )
    token = new_token()
    inv = Invitation(
        archive_id=owner.archive_id,
        email=email.strip(),
        role=role,
        is_executor=executor,
        token_hash=token_hash(token),
        expires_at=utcnow() + timedelta(days=s.invitation_days),
    )
    session.add(inv)
    session.flush()
    audit.record(
        session,
        "invitation.created",
        archive_id=owner.archive_id,
        actor_id=owner.id,
        invitation_id=inv.id,
        email=inv.email,
        role=role,
    )
    session.commit()
    return inv, f"{s.public_url.rstrip('/')}/invite/{token}"


def pending(session: Session, archive_id: int) -> list[Invitation]:
    return list(
        session.scalars(
            select(Invitation)
            .where(
                Invitation.archive_id == archive_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.expires_at > func.now(),
            )
            .order_by(Invitation.created_at.desc())
        )
    )


def revoke(session: Session, owner: User, invitation_id: int) -> None:
    inv = session.get(Invitation, invitation_id)
    if inv is None or inv.archive_id != owner.archive_id:
        raise ApiError(404, "not_found", "No such invitation.")
    inv.revoked_at = utcnow()
    audit.record(
        session,
        "invitation.revoked",
        archive_id=owner.archive_id,
        actor_id=owner.id,
        invitation_id=inv.id,
    )
    session.commit()


def usable(session: Session, token: str) -> Invitation:
    """The invitation behind a link, if it can still be used."""
    inv = session.scalars(
        select(Invitation).where(Invitation.token_hash == token_hash(token))
    ).first()
    if (
        inv is None
        or inv.accepted_at is not None
        or inv.revoked_at is not None
        or inv.expires_at <= utcnow()
    ):
        raise ApiError(410, "invitation_gone", GONE)
    return inv


def preview(session: Session, token: str) -> dict:
    inv = usable(session, token)
    inviter = session.get(User, inv.created_by) if inv.created_by else None
    return {
        "email": inv.email,
        "role": inv.role,
        "archive_name": session.get(Archive, inv.archive_id).name,
        "invited_by": inviter.display_name if inviter else None,
    }


def accept(
    session: Session,
    token: str,
    display_name: str,
    password: str,
    *,
    ip: str,
    user_agent: str | None,
):
    """Create the account and sign it in. Returns (user, session row, session token)."""
    inv = usable(session, token)
    if find_user(session, inv.email):
        raise ApiError(409, "already_a_user", "Someone already uses that email.")
    check_rules(password, inv.email)
    user = User(
        archive_id=inv.archive_id,
        email=inv.email,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        role=inv.role,
        is_executor=inv.is_executor,
        created_by=inv.created_by,
    )
    session.add(user)
    session.flush()
    inv.accepted_at = utcnow()
    inv.accepted_user_id = user.id
    audit.record(
        session,
        "invitation.accepted",
        archive_id=inv.archive_id,
        actor_id=user.id,
        subject_user_id=user.id,
        invitation_id=inv.id,
        ip=ip,
    )
    session.commit()
    row, raw = sessions.start(session, user, ip, user_agent)
    return user, row, raw
