"""OAuth for agents: discovery, registration, consent with PKCE, tokens, refresh,
revocation, and what refuses them."""

from datetime import timedelta

from sqlalchemy import update

from app.accounts.models import AuditEvent, Role
from app.agents import consent
from app.agents.models import AgentGrant, OAuthCode
from app.agents.oauth import AuthorizeRequest
from app.core.db import utcnow
from tests.accounts import member, owner
from tests.agents import (
    CALLBACK,
    RESOURCE,
    agent_client,
    authorize_params,
    code_from,
    connect,
    register,
    rpc,
    sign_in_to_connect,
    token,
)
from tests.conftest import ORIGIN, make_client


def test_discovery_documents_are_where_clients_look(engine):
    c = agent_client()
    for path in (
        "/.well-known/oauth-authorization-server/memoir",
        "/.well-known/oauth-authorization-server",
    ):
        meta = c.get(path).json()
        assert meta["issuer"] == f"{ORIGIN}/memoir"
        assert meta["token_endpoint"] == f"{ORIGIN}/memoir/api/oauth/token"
        assert meta["registration_endpoint"].endswith("/api/oauth/register")
        assert meta["code_challenge_methods_supported"] == ["S256"]
    for path in (
        "/.well-known/oauth-protected-resource/memoir/mcp",
        "/.well-known/oauth-protected-resource/mcp",
    ):
        meta = c.get(path).json()
        assert meta["resource"] == RESOURCE
        assert meta["authorization_servers"] == [f"{ORIGIN}/memoir"]


def test_the_mcp_endpoint_asks_for_a_token_and_says_where_to_get_one(engine):
    r = agent_client().post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == (
        'Bearer resource_metadata="'
        f'{ORIGIN}/.well-known/oauth-protected-resource/memoir/mcp"'
    )
    r = rpc(agent_client(), "not-a-token", "tools/list")
    assert r.status_code == 401
    assert 'error="invalid_token"' in r.headers["www-authenticate"]


def test_registration_takes_only_allowed_redirects(engine):
    c = agent_client()
    public = register(c)
    assert public["client_name"] == "Claude"
    assert "client_secret" not in public
    secret = register(c, method="client_secret_post")
    assert secret["client_secret"]
    assert register(c, uris=["http://127.0.0.1:33418/callback"])["client_id"]
    r = c.post(
        "/api/oauth/register", json={"redirect_uris": ["https://evil.example/cb"]}
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_redirect_uri"
    r = c.post("/api/oauth/register", json={"client_name": "No redirects"})
    assert r.json()["error"] == "invalid_redirect_uri"


def test_the_consent_page_names_the_agent_and_where_it_returns(engine):
    client = register(agent_client(), "Claude <b>")
    r = make_client().get(
        "/api/oauth/authorize", params=authorize_params(client["client_id"])
    )
    assert r.status_code == 200
    assert "Connect Claude &lt;b&gt; to Memoir" in r.text
    assert "claude.ai" in r.text
    assert r.headers["x-frame-options"] == "DENY"


def test_the_consent_form_carries_every_field_of_the_request(engine):
    assert set(consent.CARRIED) == set(AuthorizeRequest.model_fields)


def test_a_bad_client_or_redirect_is_shown_not_followed(engine):
    browser = make_client()
    r = browser.get("/api/oauth/authorize", params=authorize_params("nobody"))
    assert r.status_code == 400
    assert "does not know this app" in r.text
    client = register(agent_client())
    params = authorize_params(client["client_id"], redirect_uri="https://evil.example/")
    r = browser.get("/api/oauth/authorize", params=params, follow_redirects=False)
    assert r.status_code == 400


def test_pkce_is_required(engine):
    client = register(agent_client())
    params = authorize_params(client["client_id"], code_challenge_method="plain")
    r = make_client().get("/api/oauth/authorize", params=params, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith(f"{CALLBACK}?error=invalid_request")


def test_the_whole_flow_register_consent_token_refresh_revoke(session):
    owner(session)
    c = agent_client()
    client = register(c)
    code = code_from(
        sign_in_to_connect(make_client(), client["client_id"], "owner@example.org")
    )
    r = token(c, client["client_id"], code)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["token_type"] == "Bearer" and first["expires_in"] == 3600
    assert r.headers["cache-control"] == "no-store"
    assert rpc(c, first["access_token"], "tools/list").status_code == 200

    data = {"grant_type": "refresh_token", "refresh_token": first["refresh_token"]}
    r = c.post("/api/oauth/token", data=data | {"client_id": client["client_id"]})
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["refresh_token"] != first["refresh_token"]
    again = c.post("/api/oauth/token", data=data | {"client_id": client["client_id"]})
    assert again.json()["error"] == "invalid_grant"

    r = c.post(
        "/api/oauth/revoke",
        data={"token": second["refresh_token"], "client_id": client["client_id"]},
    )
    assert r.status_code == 200
    assert rpc(c, second["access_token"], "tools/list").status_code == 401
    kinds = [e.kind for e in session.query(AuditEvent).all()]
    assert "agent.connected" in kinds


def test_a_confidential_client_must_send_its_secret(session):
    owner(session)
    c = agent_client()
    client = register(c, method="client_secret_basic")
    code = code_from(
        sign_in_to_connect(make_client(), client["client_id"], "owner@example.org")
    )
    r = token(c, client["client_id"], code)
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_client"
    code = code_from(
        sign_in_to_connect(make_client(), client["client_id"], "owner@example.org")
    )
    r = c.post(
        "/api/oauth/token",
        auth=(client["client_id"], client["client_secret"]),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": "a-verifier-that-is-long-enough-for-pkce-0123456789",
            "redirect_uri": CALLBACK,
        },
    )
    assert r.status_code == 200, r.text


def test_a_bad_verifier_a_wrong_redirect_or_an_old_code_is_refused(session):
    owner(session)
    c = agent_client()
    client = register(c)
    cid = client["client_id"]

    def fresh():
        return code_from(sign_in_to_connect(make_client(), cid, "owner@example.org"))

    assert token(c, cid, fresh(), verifier="x" * 50).json()["error"] == "invalid_grant"
    wrong = token(
        c, cid, fresh(), redirect_uri="https://claude.com/api/mcp/auth_callback"
    )
    assert wrong.json()["error"] == "invalid_grant"
    old = fresh()
    session.execute(
        update(OAuthCode).values(expires_at=utcnow() - timedelta(seconds=1))
    )
    session.commit()
    assert token(c, cid, old).json()["error"] == "invalid_grant"


def test_a_code_used_twice_ends_the_connection(session):
    owner(session)
    c = agent_client()
    client = register(c)
    code = code_from(
        sign_in_to_connect(make_client(), client["client_id"], "owner@example.org")
    )
    tokens = token(c, client["client_id"], code).json()
    assert token(c, client["client_id"], code).json()["error"] == "invalid_grant"
    assert rpc(c, tokens["access_token"], "tools/list").status_code == 401


def test_a_wrong_password_or_a_pending_password_change_connects_nothing(session):
    owner(session)
    pending = member(session, Role.CONTRIBUTOR)
    pending.must_change_password = True
    session.commit()
    client = register(agent_client())
    r = sign_in_to_connect(
        make_client(), client["client_id"], "owner@example.org", "wrong"
    )
    assert r.status_code == 401
    assert "do not match an account" in r.text
    assert 'value="owner@example.org"' in r.text
    r = sign_in_to_connect(
        make_client(), client["client_id"], "contributor@example.org"
    )
    assert r.status_code == 403
    assert "Choose a new password" in r.text
    assert session.query(AgentGrant).count() == 0


def test_the_login_rate_limit_covers_the_consent_page(session):
    owner(session)
    client = register(agent_client())
    for _ in range(5):
        sign_in_to_connect(
            make_client(), client["client_id"], "owner@example.org", "no"
        )
    r = sign_in_to_connect(make_client(), client["client_id"], "owner@example.org")
    assert r.status_code == 401


def test_cancel_sends_the_person_back_with_access_denied(session):
    owner(session)
    client = register(agent_client())
    r = make_client().post(
        "/api/oauth/authorize",
        data=authorize_params(client["client_id"]) | {"decision": "deny"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "error=access_denied" in r.headers["location"]
    assert "state=xyz" in r.headers["location"]


def test_the_consent_form_keeps_the_origin_check(session):
    owner(session)
    client = register(agent_client())
    form = authorize_params(client["client_id"]) | {
        "email": "owner@example.org",
        "password": "correct horse battery",
    }
    r = agent_client().post(
        "/api/oauth/authorize",
        data=form,
        headers={"Origin": "https://evil.example"},
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_an_unknown_resource_is_refused(session):
    owner(session)
    c = agent_client()
    tokens = connect("owner@example.org")
    r = c.post(
        "/api/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": tokens["client_id"],
            "resource": "https://elsewhere.example/mcp",
        },
    )
    assert r.json()["error"] == "invalid_target"
