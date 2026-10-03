"""Users, their sessions, invitations, login attempts and the audit log."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audited import Audited
from app.core.db import Base, Timestamped, utcnow


class Role(StrEnum):
    """What a user may do, each including the ones below it.

    Executor is not a role but a separate grant (`User.is_executor`).
    """

    OWNER = "owner"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"


RANK = {Role.VIEWER: 0, Role.CONTRIBUTOR: 1, Role.OWNER: 2}


class User(Audited, Timestamped, Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", func.lower("email"), unique=True),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    archive_id: Mapped[int] = mapped_column(
        ForeignKey("archives.id", ondelete="RESTRICT"), index=True
    )
    email: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default=Role.CONTRIBUTOR)
    # The executor opens the sealed queue and carries out legacy wishes (requirements
    # section 15).
    is_executor: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set by the owner's temporary password: nothing works until they pick their own.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)

    def at_least(self, role: Role) -> bool:
        return RANK[Role(self.role)] >= RANK[role]


class UserSession(Base):
    """A signed-in browser. The cookie holds a random token; only its hash is kept."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Sent back by the web app in a header on every change: the CSRF token.
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(String(64))


class Invitation(Audited, Timestamped, Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    archive_id: Mapped[int] = mapped_column(
        ForeignKey("archives.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    is_executor: Mapped[bool] = mapped_column(Boolean, default=False)
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginAttempt(Base):
    """Every login attempt, for the rate limits. Rows are only ever counted."""

    __tablename__ = "login_attempts"
    __table_args__ = (
        Index("ix_login_attempts_ip_time", "ip", "created_at"),
        Index("ix_login_attempts_email_time", "email", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ip: Mapped[str] = mapped_column(String(64))
    email: Mapped[str] = mapped_column(String(255))
    succeeded: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AuditEvent(Base):
    """Logins, invitations, role changes and password resets: who did what to whom."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    archive_id: Mapped[int | None] = mapped_column(
        ForeignKey("archives.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(60), index=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    subject_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    ip: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
