from app.accounts.models import Role
from tests.accounts import member, owner, sign_in
from tests.conftest import make_client


def kinds(client) -> list[str]:
    return [e["kind"] for e in client.get("/api/audit").json()]


def test_the_audit_log_records_logins_invitations_roles_and_resets(session):
    owner(session)
    mary = member(session, Role.VIEWER, "mary@example.org")
    make_client().post(
        "/api/auth/login", json={"email": "owner@example.org", "password": "x" * 12}
    )
    o = sign_in("owner@example.org")
    link = o.post("/api/invitations", json={"email": "ann@example.org"}).json()["link"]
    make_client().post(
        f"/api/invitations/accept/{link.rsplit('/', 1)[1]}",
        json={"display_name": "Ann", "password": "anns own phrase"},
    )
    o.patch(f"/api/users/{mary.id}", json={"role": "contributor"})
    o.post(
        f"/api/users/{mary.id}/temporary-password", json={"password": "temporary 2026!"}
    )
    o.post("/api/auth/logout-all")
    assert kinds(o) == [
        "logout.everywhere",
        "password.reset",
        "role.changed",
        "invitation.accepted",
        "invitation.created",
        "login.succeeded",
        "login.failed",
        "owner.created",
    ]
    change = o.get("/api/audit").json()[2]
    assert change["detail"] == {"old": "viewer", "new": "contributor"}
    assert change["subject_user_id"] == mary.id


def test_rows_record_who_made_and_changed_them(session):
    from app.accounts.models import Invitation

    me = owner(session)
    o = sign_in("owner@example.org")
    o.post("/api/invitations", json={"email": "ann@example.org"})
    inv = session.query(Invitation).one()
    assert (inv.created_by, inv.updated_by) == (me.id, me.id)
    assert inv.updated_at is not None
