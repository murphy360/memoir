"""Memoir as its own OAuth 2.1 authorisation server, for agents (docs/AGENTS_MCP.md).

Discovery (RFC 8414, RFC 9728), dynamic client registration (RFC 7591), the consent
page (authorization code with PKCE S256), the token endpoint (codes and refresh
tokens) and revocation (RFC 7009). Errors here have OAuth's shape,
{"error": "...", "error_description": "..."}, because agents read them.
"""

import base64
import binascii
import logging
from typing import Annotated
from urllib.parse import unquote, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Body, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.accounts.deps import client_ip
from app.accounts.login import check_password
from app.agents import consent, grants
from app.agents.grants import OAuthError
from app.agents.models import OAuthClient
from app.core.db import get_session
from app.core.errors import ApiError
from app.core.settings import Settings, get_settings

log = logging.getLogger(__name__)
PREFIX = "/api/oauth"
METHODS = ("none", "client_secret_post", "client_secret_basic")
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
# Desktop assistants listen on this computer for the redirect (RFC 8252).
LOOPBACK = ("localhost", "127.0.0.1", "::1")
router = APIRouter(prefix=PREFIX, tags=["oauth"])


def resource_url(settings: Settings) -> str:
    return f"{settings.base_url}/mcp"


def base_path(settings: Settings) -> str:
    return urlsplit(settings.base_url).path.rstrip("/")


def server_metadata(settings: Settings) -> dict:
    at = settings.base_url + PREFIX
    return {
        "issuer": settings.base_url,
        "authorization_endpoint": f"{at}/authorize",
        "token_endpoint": f"{at}/token",
        "registration_endpoint": f"{at}/register",
        "revocation_endpoint": f"{at}/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": list(METHODS),
        "revocation_endpoint_auth_methods_supported": list(METHODS),
    }


def resource_metadata(settings: Settings) -> dict:
    return {
        "resource": resource_url(settings),
        "authorization_servers": [settings.base_url],
        "bearer_methods_supported": ["header"],
        "resource_name": "Memoir",
    }


def resource_metadata_url(settings: Settings) -> str:
    origin = settings.base_url[: len(settings.base_url) - len(base_path(settings))]
    return f"{origin}/.well-known/oauth-protected-resource{base_path(settings)}/mcp"


def well_known(settings: Settings) -> APIRouter:
    """The discovery documents. A client looks for them at the host's root, with the
    issuer's path after the well-known name (`/.well-known/oauth-authorization-server
    /memoir`); behind the proxy without it, too. Not in the OpenAPI document: the
    paths depend on where Memoir is served."""
    found = APIRouter(include_in_schema=False)
    path = base_path(settings)
    for at in {
        f"/.well-known/oauth-authorization-server{path}",
        "/.well-known/oauth-authorization-server",
    }:
        found.add_api_route(at, lambda: server_metadata(get_settings()))
    for at in {
        f"/.well-known/oauth-protected-resource{path}/mcp",
        "/.well-known/oauth-protected-resource/mcp",
    }:
        found.add_api_route(at, lambda: resource_metadata(get_settings()))
    return found


async def error_response(_: Request, exc: OAuthError) -> JSONResponse:
    body = {"error": exc.error, "error_description": exc.description}
    headers = dict(NO_STORE)
    if exc.status == 401:
        headers["WWW-Authenticate"] = 'Basic realm="memoir"'
    return JSONResponse(body, exc.status, headers=headers)


def _redirect_allowed(uri: str, settings: Settings) -> bool:
    if uri in settings.redirect_uris:
        return True
    parts = urlsplit(uri)
    return parts.scheme == "http" and parts.hostname in LOOPBACK


@router.post("/register", status_code=201)
def register(
    body: dict = Body(..., examples=[{"client_name": "Claude", "redirect_uris": []}]),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """Dynamic client registration. Open, but only for the redirects Memoir allows."""
    uris = body.get("redirect_uris")
    if not isinstance(uris, list) or not uris or len(uris) > 10:
        raise OAuthError("invalid_redirect_uri", "Send one to ten redirect_uris.")
    for uri in uris:
        if not isinstance(uri, str) or len(uri) > 500:
            raise OAuthError("invalid_redirect_uri", "A redirect_uri is not valid.")
        if not _redirect_allowed(uri, settings):
            raise OAuthError(
                "invalid_redirect_uri", f"Memoir does not send people to {uri}."
            )
    method = body.get("token_endpoint_auth_method") or "client_secret_basic"
    if method not in METHODS:
        raise OAuthError(
            "invalid_client_metadata", f"Use one of: {', '.join(METHODS)}."
        )
    name = " ".join(str(body.get("client_name") or "An agent").split())[:120]
    client, secret = grants.register(db, name or "An agent", uris, method)
    log.info("oauth client registered client=%s", client.client_id)
    out = {
        "client_id": client.client_id,
        "client_id_issued_at": int(client.created_at.timestamp()),
        "client_name": client.client_name,
        "redirect_uris": uris,
        "token_endpoint_auth_method": method,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }
    if secret:
        out |= {"client_secret": secret, "client_secret_expires_at": 0}
    return JSONResponse(out, 201, headers=NO_STORE)


class AuthorizeRequest(BaseModel):
    """The authorization request, as the agent sends it and as the form carries it."""

    response_type: str = ""
    client_id: str = ""
    redirect_uri: str = ""
    code_challenge: str = ""
    code_challenge_method: str = ""
    state: str = ""
    scope: str = ""
    resource: str = ""


class ConsentForm(AuthorizeRequest):
    email: str = ""
    password: str = ""
    decision: str = "allow"


class Refused(Exception):
    """Sent back to the agent's redirect_uri as ?error=..."""

    def __init__(self, uri: str, error: str, description: str, state: str):
        super().__init__(description)
        self.uri, self.error, self.description, self.state = (
            uri,
            error,
            description,
            state,
        )


def back_to(uri: str, state: str, **params: str) -> RedirectResponse:
    parts = urlsplit(uri)
    if state:
        params["state"] = state
    query = "&".join(q for q in (parts.query, urlencode(params)) if q)
    return RedirectResponse(urlunsplit(parts._replace(query=query)), 302)


def _same_resource(value: str, settings: Settings) -> bool:
    return value.rstrip("/") == resource_url(settings)


def check_request(
    db: Session, req: AuthorizeRequest, settings: Settings
) -> OAuthClient:
    """The client, once the request is one Memoir will answer. A bad client or
    redirect is shown on the page (sending anyone there would be unsafe); anything
    else goes back to the agent."""
    client = grants.client_by_id(db, req.client_id)
    if client is None:
        raise ApiError(400, "unknown_client", "Memoir does not know this app.")
    if not req.redirect_uri and len(client.redirect_uris) == 1:
        req.redirect_uri = client.redirect_uris[0]
    if req.redirect_uri not in client.redirect_uris:
        raise ApiError(
            400, "bad_redirect", "This app asked to return somewhere it did not name."
        )
    if req.response_type != "code":
        raise Refused(
            req.redirect_uri, "unsupported_response_type", "Only code.", req.state
        )
    if req.code_challenge_method != "S256" or not (
        43 <= len(req.code_challenge) <= 128
    ):
        raise Refused(
            req.redirect_uri,
            "invalid_request",
            "PKCE with S256 is required.",
            req.state,
        )
    if req.resource and not _same_resource(req.resource, settings):
        raise Refused(
            req.redirect_uri, "invalid_target", "Unknown resource.", req.state
        )
    return client


def _consent_or_problem(db, req: AuthorizeRequest, settings: Settings):
    try:
        return check_request(db, req, settings), None
    except ApiError as exc:
        return None, consent.problem(exc.message)
    except Refused as exc:
        return None, back_to(
            exc.uri, exc.state, error=exc.error, error_description=exc.description
        )


@router.get("/authorize", response_class=Response)
def authorize(
    req: Annotated[AuthorizeRequest, Query()],
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """The consent page: the person signs in to connect the agent."""
    client, answer = _consent_or_problem(db, req, settings)
    if answer is not None:
        return answer
    return consent.form(
        f"{settings.base_url}{PREFIX}/authorize", client.client_name, req.model_dump()
    )


@router.post("/authorize", response_class=Response)
def allow(
    body: Annotated[ConsentForm, Form()],
    request: Request,
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """The consent form. The web app's origin check guards it like any change."""
    client, answer = _consent_or_problem(db, body, settings)
    if answer is not None:
        return answer
    if body.decision != "allow":
        return back_to(body.redirect_uri, body.state, error="access_denied")
    again = {
        "action": f"{settings.base_url}{PREFIX}/authorize",
        "client_name": client.client_name,
        "fields": body.model_dump(),
        "email": body.email,
    }
    try:
        user = check_password(
            db,
            body.email,
            body.password,
            ip=client_ip(request),
            settings=settings,
            kind="agent.connected",
            client_id=client.client_id,
            client_name=client.client_name,
        )
    except ApiError as exc:
        return consent.form(**again, error=exc.message, status=401)
    if user.must_change_password:
        db.rollback()
        message = "Choose a new password in Memoir first, then connect again."
        return consent.form(**again, error=message, status=403)
    grant = grants.connect(db, user, client)
    code = grants.new_code(db, grant, body.redirect_uri, body.code_challenge)
    log.info("agent connected client=%s grant=%s", client.client_id, grant.id)
    return back_to(body.redirect_uri, body.state, code=code)


class TokenForm(BaseModel):
    grant_type: str = ""
    code: str | None = None
    redirect_uri: str | None = None
    code_verifier: str | None = None
    refresh_token: str | None = None
    resource: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


class RevokeForm(BaseModel):
    token: str = ""
    token_type_hint: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


def _client_credentials(request: Request, form) -> tuple[str | None, str | None]:
    """client_secret_basic (an Authorization header) or client_secret_post."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        try:
            pair = base64.b64decode(header[6:].strip()).decode()
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise OAuthError("invalid_client", "Bad client credentials.", 401) from exc
        name, _, secret = pair.partition(":")
        return unquote(name), unquote(secret)
    return form.client_id, form.client_secret


@router.post("/token")
def token(
    body: Annotated[TokenForm, Form()],
    request: Request,
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """Codes and refresh tokens, for access tokens."""
    client = grants.authenticate(db, *_client_credentials(request, body))
    if body.resource and not _same_resource(body.resource, settings):
        raise OAuthError("invalid_target", "Unknown resource.")
    if body.grant_type == "authorization_code":
        issued = grants.exchange_code(
            db, client, body.code, body.code_verifier, body.redirect_uri, settings
        )
    elif body.grant_type == "refresh_token":
        issued = grants.refresh(db, client, body.refresh_token, settings)
    else:
        raise OAuthError("unsupported_grant_type", "Use authorization_code.")
    log.info("oauth token issued client=%s grant=%s", client.client_id, body.grant_type)
    return JSONResponse(issued, headers=NO_STORE)


@router.post("/revoke")
def revoke(
    body: Annotated[RevokeForm, Form()],
    request: Request,
    db: Session = Depends(get_session),
):
    """RFC 7009: always 200 once the client is known."""
    client = grants.authenticate(db, *_client_credentials(request, body))
    grants.revoke(db, client, body.token)
    log.info("oauth token revoked client=%s", client.client_id)
    return JSONResponse({}, headers=NO_STORE)
