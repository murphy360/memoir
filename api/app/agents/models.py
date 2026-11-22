"""Connected agents: OAuth clients, each person's grant to one, codes and tokens.

A client is an app that registered itself (claude.ai, a desktop assistant). A grant is
one person's "yes" to one client: the profile page lists grants as "Connected agents".
Codes and tokens belong to a grant; the database keeps only their SHA-256 hashes.
"""

from datetime import datetime

from sqlalchemy import CHAR, BigInteger, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, utcnow


class OAuthClient(Base):
    """An app that registered itself (RFC 7591). Not tied to anyone until a person
    signs in through it."""

    __tablename__ = "oauth_clients"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), unique=True)
    # Shown on the consent page, the profile page and beside every memory it wrote.
    client_name: Mapped[str] = mapped_column(String(120))
    redirect_uris: Mapped[list] = mapped_column(JSONB)
    # none (a public client using PKCE alone), client_secret_post or _basic.
    auth_method: Mapped[str] = mapped_column(String(32))
    secret_hash: Mapped[str | None] = mapped_column(CHAR(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AgentGrant(Base):
    """One person's connection of one client: what Disconnect ends."""

    __tablename__ = "agent_grants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("oauth_clients.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OAuthCode(Base):
    """An authorization code: five minutes, once, for the redirect it was made for."""

    __tablename__ = "oauth_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    grant_id: Mapped[int] = mapped_column(
        ForeignKey("agent_grants.id", ondelete="CASCADE"), index=True
    )
    redirect_uri: Mapped[str] = mapped_column(String(500))
    code_challenge: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OAuthToken(Base):
    """An access token (an hour) or a refresh token (90 days, replaced on each use)."""

    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    grant_id: Mapped[int] = mapped_column(
        ForeignKey("agent_grants.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
