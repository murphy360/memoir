"""What the OAuth endpoints issue, and who a bearer token speaks for.

Codes and tokens are random strings; only their SHA-256 hashes are stored. A grant is a
person's connection of one client. Disconnecting it, removing the person, or a new
password ends every code and token under it at once.
"""

import base64
import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.accounts.tokens import new_token, token_hash
from app.agents.models import AgentGrant, OAuthClient, OAuthCode, OAuthToken
from app.core.db import utcnow
from app.core.errors import ApiError
from app.core.settings import Settings

ACCESS, REFRESH = "access", "refresh"
CODE_TTL = timedelta(minutes=5)
# last_used_at is written at most this often, so a busy agent is not a write per call.
TOUCH_EVERY = timedelta(minutes=1)
VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


class OAuthError(Exception):
    """An OAuth error response (RFC 6749 section 5.2): a code and a sentence."""

    def __init__(self, error: str, description: str, status: int = 400):
        super().__init__(description)
        self.error, self.description, self.status = error, description, status


@dataclass
class Caller:
    """Who an access token speaks for: the person, through which client."""

    user: User
    grant: AgentGrant
    client: OAuthClient


def usable(user: User | None) -> bool:
    """A person an agent may act as: present, and not waiting to pick a password."""
    return (
        user is not None and user.deleted_at is None and not user.must_change_password
    )


def register(
    session: Session, name: str, redirect_uris: list[str], auth_method: str
) -> tuple[OAuthClient, str | None]:
    """A new client; returns it and its secret (None for a public client)."""
    secret = None if auth_method == "none" else new_token()
    client = OAuthClient(
        client_id=str(uuid.uuid4()),
        client_name=name,
        redirect_uris=redirect_uris,
        auth_method=auth_method,
        secret_hash=token_hash(secret) if secret else None,
    )
    session.add(client)
    session.commit()
    return client, secret


def client_by_id(session: Session, client_id: str | None) -> OAuthClient | None:
    if not client_id:
        return None
    return session.scalars(
        select(OAuthClient).where(OAuthClient.client_id == client_id[:64])
    ).first()


def authenticate(
    session: Session, client_id: str | None, secret: str | None
) -> OAuthClient:
    """The client making a token or revoke request, with its secret checked."""
    client = client_by_id(session, client_id)
    if client is None:
        raise OAuthError("invalid_client", "Unknown client.", 401)
    if client.secret_hash and not (
        secret and secrets.compare_digest(token_hash(secret), client.secret_hash)
    ):
        raise OAuthError("invalid_client", "The client secret is wrong.", 401)
    return client


def connect(session: Session, user: User, client: OAuthClient) -> AgentGrant:
    """The person's live grant to this client, made the first time."""
    grant = session.scalars(
        select(AgentGrant).where(
            AgentGrant.user_id == user.id,
            AgentGrant.client_id == client.id,
            AgentGrant.revoked_at.is_(None),
        )
    ).first()
    if grant is None:
        grant = AgentGrant(user_id=user.id, client_id=client.id)
        session.add(grant)
        session.flush()
    return grant


def new_code(
    session: Session, grant: AgentGrant, redirect_uri: str, challenge: str
) -> str:
    now = utcnow()
    session.execute(delete(OAuthCode).where(OAuthCode.expires_at < now))
    code = new_token()
    session.add(
        OAuthCode(
            code_hash=token_hash(code),
            grant_id=grant.id,
            redirect_uri=redirect_uri,
            code_challenge=challenge,
            expires_at=now + CODE_TTL,
        )
    )
    session.commit()
    return code


def pkce_matches(verifier: str | None, challenge: str) -> bool:
    if not verifier or not VERIFIER.match(verifier):
        return False
    digest = hashlib.sha256(verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return secrets.compare_digest(expected, challenge)


def _live_grant(session: Session, grant_id: int, client: OAuthClient) -> AgentGrant:
    grant = session.get(AgentGrant, grant_id)
    if grant is None or grant.revoked_at or grant.client_id != client.id:
        raise OAuthError("invalid_grant", "This connection was ended.")
    if not usable(session.get(User, grant.user_id)):
        raise OAuthError("invalid_grant", "This account cannot use agents now.")
    return grant


def _issue(session: Session, grant: AgentGrant, settings: Settings) -> dict:
    now = utcnow()
    access, refresh = new_token(), new_token()
    access_ttl = timedelta(minutes=settings.agent_access_minutes)
    session.execute(
        delete(OAuthToken).where(
            OAuthToken.grant_id == grant.id, OAuthToken.expires_at < now
        )
    )
    session.add_all(
        [
            OAuthToken(
                token_hash=token_hash(access),
                grant_id=grant.id,
                kind=ACCESS,
                expires_at=now + access_ttl,
            ),
            OAuthToken(
                token_hash=token_hash(refresh),
                grant_id=grant.id,
                kind=REFRESH,
                expires_at=now + timedelta(days=settings.agent_refresh_days),
            ),
        ]
    )
    grant.last_used_at = now
    session.commit()
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": int(access_ttl.total_seconds()),
        "refresh_token": refresh,
    }


def exchange_code(
    session: Session,
    client: OAuthClient,
    code: str | None,
    verifier: str | None,
    redirect_uri: str | None,
    settings: Settings,
) -> dict:
    row = session.scalars(
        select(OAuthCode).where(OAuthCode.code_hash == token_hash(code or ""))
    ).first()
    if row is None or row.expires_at <= utcnow():
        raise OAuthError("invalid_grant", "The code is unknown or expired.")
    grant = _live_grant(session, row.grant_id, client)
    if row.used_at is not None:
        # A code used twice was stolen or replayed: end what it gave (RFC 9700).
        end_grant(session, grant)
        raise OAuthError("invalid_grant", "The code was already used.")
    row.used_at = utcnow()
    session.commit()
    if redirect_uri is not None and redirect_uri != row.redirect_uri:
        raise OAuthError("invalid_grant", "The redirect_uri does not match.")
    if not pkce_matches(verifier, row.code_challenge):
        raise OAuthError("invalid_grant", "The code_verifier does not match.")
    return _issue(session, grant, settings)


def _token(session: Session, raw: str | None) -> OAuthToken | None:
    if not raw:
        return None
    return session.scalars(
        select(OAuthToken).where(OAuthToken.token_hash == token_hash(raw))
    ).first()


def refresh(
    session: Session, client: OAuthClient, raw: str | None, settings: Settings
) -> dict:
    """New tokens for a refresh token, which is used up (rotation)."""
    row = _token(session, raw)
    if (
        row is None
        or row.kind != REFRESH
        or row.revoked_at is not None
        or row.expires_at <= utcnow()
    ):
        raise OAuthError("invalid_grant", "The refresh token is unknown or expired.")
    grant = _live_grant(session, row.grant_id, client)
    row.revoked_at = utcnow()
    return _issue(session, grant, settings)


def revoke(session: Session, client: OAuthClient, raw: str | None) -> None:
    """RFC 7009. A refresh token ends the whole connection; an access token, itself.
    Unknown tokens are ignored."""
    row = _token(session, raw)
    grant = session.get(AgentGrant, row.grant_id) if row else None
    if row is None or grant is None or grant.client_id != client.id:
        return
    if row.kind == REFRESH:
        end_grant(session, grant)
    else:
        row.revoked_at = utcnow()
        session.commit()


def caller(session: Session, raw: str | None) -> Caller | None:
    """Who a bearer token speaks for; None when it should get a 401."""
    row = _token(session, raw)
    now = utcnow()
    if row is None or row.kind != ACCESS or row.revoked_at or row.expires_at <= now:
        return None
    grant = session.get(AgentGrant, row.grant_id)
    user = session.get(User, grant.user_id) if grant else None
    if grant is None or grant.revoked_at is not None or not usable(user):
        return None
    if grant.last_used_at is None or now - grant.last_used_at >= TOUCH_EVERY:
        grant.last_used_at = now
        session.commit()
    return Caller(user, grant, session.get(OAuthClient, grant.client_id))


def end_grant(session: Session, grant: AgentGrant) -> None:
    now = utcnow()
    grant.revoked_at = grant.revoked_at or now
    session.execute(
        update(OAuthToken)
        .where(OAuthToken.grant_id == grant.id, OAuthToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    session.commit()


def connected(session: Session, user: User) -> list[tuple[AgentGrant, OAuthClient]]:
    """The person's live connections, most recently used first."""
    rows = session.execute(
        select(AgentGrant, OAuthClient)
        .join(OAuthClient, OAuthClient.id == AgentGrant.client_id)
        .where(AgentGrant.user_id == user.id, AgentGrant.revoked_at.is_(None))
        .order_by(AgentGrant.last_used_at.desc().nulls_last(), AgentGrant.id.desc())
    )
    return [(g, c) for g, c in rows]


def disconnect(session: Session, user: User, grant_id: int) -> None:
    grant = session.get(AgentGrant, grant_id)
    if grant is None or grant.user_id != user.id or grant.revoked_at is not None:
        raise ApiError(404, "not_found", "No such connected agent.")
    end_grant(session, grant)


def end_all(session: Session, user_id: int) -> None:
    """Disconnect every agent of a person (a new password, removal). Commits."""
    for grant in session.scalars(
        select(AgentGrant).where(
            AgentGrant.user_id == user_id, AgentGrant.revoked_at.is_(None)
        )
    ).all():
        end_grant(session, grant)
