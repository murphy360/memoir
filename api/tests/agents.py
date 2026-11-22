"""Helpers for the agent tests: an agent registers, a person connects it, it calls
tools. The agent's own servers send no Origin header, so its client sends none."""

import atexit
import base64
import contextlib
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from app.main import create_app
from tests.accounts import PASSWORD
from tests.conftest import ORIGIN

CALLBACK = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "a-verifier-that-is-long-enough-for-pkce-0123456789"
RESOURCE = f"{ORIGIN}/memoir/mcp"


def challenge(verifier: str = VERIFIER) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


_STARTED = contextlib.ExitStack()
atexit.register(_STARTED.close)
_agent: list[TestClient] = []


def agent_client() -> TestClient:
    """An agent's servers: no Origin, no cookies. Started once (the MCP transport runs
    in the app's lifespan) and shared by every test."""
    if not _agent:
        _agent.append(_STARTED.enter_context(TestClient(create_app(), base_url=ORIGIN)))
    _agent[0].cookies.clear()
    return _agent[0]


def register(c, name="Claude", method="none", uris=(CALLBACK,)) -> dict:
    r = c.post(
        "/api/oauth/register",
        json={
            "client_name": name,
            "redirect_uris": list(uris),
            "token_endpoint_auth_method": method,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def authorize_params(client_id: str, **extra) -> dict:
    return {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": CALLBACK,
        "code_challenge": challenge(),
        "code_challenge_method": "S256",
        "state": "xyz",
        "resource": RESOURCE,
        **extra,
    }


def sign_in_to_connect(browser, client_id: str, email: str, password=PASSWORD, **kw):
    """The person's browser posting the consent form."""
    form = authorize_params(client_id, **kw) | {"email": email, "password": password}
    return browser.post("/api/oauth/authorize", data=form, follow_redirects=False)


def code_from(response) -> str:
    assert response.status_code == 302, response.text
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["state"] == ["xyz"]
    return query["code"][0]


def token(c, client_id: str, code: str, verifier=VERIFIER, **extra):
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": CALLBACK,
        "client_id": client_id,
        "resource": RESOURCE,
        **extra,
    }
    return c.post("/api/oauth/token", data=data)


def connect(email: str, name: str = "Claude") -> dict:
    """An agent connected by `email`: its client id and tokens."""
    from tests.conftest import make_client

    c = agent_client()
    client = register(c, name)
    code = code_from(sign_in_to_connect(make_client(), client["client_id"], email))
    r = token(c, client["client_id"], code)
    assert r.status_code == 200, r.text
    return {"client_id": client["client_id"], **r.json()}


def rpc(c, access: str, method: str, params: dict | None = None):
    return c.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers={
            "Authorization": f"Bearer {access}",
            "Accept": "application/json, text/event-stream",
        },
    )


def call(c, access: str, tool: str, **arguments) -> tuple[bool, object]:
    """A tool call: (is_error, the result as data, or the error's text)."""
    r = rpc(c, access, "tools/call", {"name": tool, "arguments": arguments})
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    text = result["content"][0]["text"]
    return result["isError"], text if result["isError"] else json.loads(text)


def tool_names(c, access: str) -> set[str]:
    r = rpc(c, access, "tools/list")
    assert r.status_code == 200, r.text
    return {t["name"] for t in r.json()["result"]["tools"]}
