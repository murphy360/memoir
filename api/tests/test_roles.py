"""Every route, every role: who may call what.

A new route that forgets its role check fails here.
"""

import re

import pytest

from app.accounts.models import Role
from app.main import create_app
from tests.accounts import member, owner, sign_in
from tests.conftest import make_client

# Open to everyone, signed in or not.
PUBLIC = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/login"),
    ("GET", "/api/invitations/accept/{token}"),
    ("POST", "/api/invitations/accept/{token}"),
}
# A viewer may still manage their own account.
SELF_SERVICE = {
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/logout-all"),
    ("PATCH", "/api/me"),
    ("POST", "/api/me/password"),
}
OWNER_ONLY = re.compile(r"^/api/(users|audit|invitations)(/|$)")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def routes():
    """Every route and method, from the OpenAPI document (the API's public list)."""
    for path, operations in create_app().openapi()["paths"].items():
        for method in operations:
            yield method.upper(), path


ALL = sorted(set(routes()))
assert len(ALL) > 15, "the route list is empty: the matrix would test nothing"


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


@pytest.mark.parametrize("method,path", [r for r in ALL if r not in PUBLIC])
def test_every_route_but_the_public_ones_needs_a_session(engine, method, path):
    r = make_client().request(method, concrete(path), json={})
    assert r.status_code == 401, (method, path, r.text)


@pytest.mark.parametrize(
    "method,path", [r for r in ALL if r[0] in UNSAFE and r not in PUBLIC | SELF_SERVICE]
)
def test_a_viewer_changes_nothing(session, method, path):
    owner(session)
    member(session, Role.VIEWER)
    r = sign_in("viewer@example.org").request(method, concrete(path), json={})
    assert r.status_code == 403, (method, path, r.text)
    assert r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize(
    "method,path", [r for r in ALL if OWNER_ONLY.match(r[1]) and r not in PUBLIC]
)
def test_owner_routes_refuse_a_contributor(session, method, path):
    owner(session)
    member(session, Role.CONTRIBUTOR)
    r = sign_in("contributor@example.org").request(method, concrete(path), json={})
    assert r.status_code == 403, (method, path, r.text)


def test_the_executor_grant_is_checked_separately(session):
    from app.accounts.deps import Signed, require_executor
    from app.core.errors import ApiError

    owner(session)
    plain = member(session, Role.CONTRIBUTOR, "plain@example.org")
    executor = member(session, Role.VIEWER, "exec@example.org", executor=True)
    assert require_executor(Signed(executor, None)) is executor
    with pytest.raises(ApiError):
        require_executor(Signed(plain, None))
