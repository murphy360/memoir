from datetime import timedelta

from sqlalchemy import select, update

from app.accounts.models import Invitation, Role, User
from app.core.db import utcnow
from tests.accounts import member, owner, sign_in
from tests.conftest import make_client

NEW_PASSWORD = "a long and private phrase"


def invite(c, email="mary@example.org", role="contributor", executor=False):
    r = c.post(
        "/api/invitations", json={"email": email, "role": role, "is_executor": executor}
    )
    assert r.status_code == 201, r.text
    return r.json()


def token_of(link: str) -> str:
    return link.rsplit("/", 1)[1]


def test_an_invitation_link_signs_the_new_member_in_once(session):
    owner(session)
    made = invite(sign_in("owner@example.org"), role="viewer", executor=True)
    assert made["link"].startswith("https://testserver/memoir/invite/")
    token = token_of(made["link"])
    guest = make_client()
    preview = guest.get(f"/api/invitations/accept/{token}").json()
    assert preview == {
        "email": "mary@example.org",
        "role": "viewer",
        "archive_name": "The Murphys",
        "invited_by": "Owner",
    }
    r = guest.post(
        f"/api/invitations/accept/{token}",
        json={"display_name": "Mary", "password": NEW_PASSWORD},
    )
    assert r.status_code == 200
    assert (r.json()["role"], r.json()["is_executor"]) == ("viewer", True)
    assert guest.get("/api/me").json()["display_name"] == "Mary"
    again = make_client().post(
        f"/api/invitations/accept/{token}",
        json={"display_name": "Mallory", "password": NEW_PASSWORD},
    )
    assert again.status_code == 410
    assert again.json()["error"]["code"] == "invitation_gone"


def test_an_invitation_older_than_a_week_does_not_work(session):
    owner(session)
    token = token_of(invite(sign_in("owner@example.org"))["link"])
    session.execute(
        update(Invitation).values(expires_at=utcnow() - timedelta(seconds=1))
    )
    session.commit()
    assert make_client().get(f"/api/invitations/accept/{token}").status_code == 410


def test_a_revoked_invitation_does_not_work(session):
    owner(session)
    c = sign_in("owner@example.org")
    made = invite(c)
    assert c.get("/api/invitations").json()[0]["email"] == "mary@example.org"
    assert c.delete(f"/api/invitations/{made['id']}").status_code == 204
    assert c.get("/api/invitations").json() == []
    token = token_of(made["link"])
    assert make_client().get(f"/api/invitations/accept/{token}").status_code == 410


def test_an_existing_member_cannot_be_invited_again(session):
    owner(session)
    r = sign_in("owner@example.org").post(
        "/api/invitations", json={"email": "Owner@Example.org", "role": "viewer"}
    )
    assert r.status_code == 409


def test_accepting_needs_a_good_password(session):
    owner(session)
    token = token_of(invite(sign_in("owner@example.org"))["link"])
    r = make_client().post(
        f"/api/invitations/accept/{token}",
        json={"display_name": "Mary", "password": "short"},
    )
    assert r.status_code == 422
    assert r.json()["error"] == {
        "code": "weak_password",
        "message": "Use at least 12 characters.",
        "field": "password",
    }
    assert (
        session.scalars(select(User).where(User.email == "mary@example.org")).all()
        == []
    )


def test_only_an_owner_invites(session):
    owner(session)
    member(session, Role.CONTRIBUTOR)
    r = sign_in("contributor@example.org").post(
        "/api/invitations", json={"email": "x@example.org"}
    )
    assert r.status_code == 403
