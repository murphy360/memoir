from app.accounts.models import Role
from tests.accounts import PASSWORD, member, owner, sign_in
from tests.conftest import make_client

TEMP = "temporary phrase 2026"
MINE = "my own new phrase"


def test_a_temporary_password_must_be_changed_before_anything_else(session):
    owner(session)
    mary = member(session, Role.CONTRIBUTOR, "mary@example.org")
    o = sign_in("owner@example.org")
    old = sign_in("mary@example.org")
    r = o.post(f"/api/users/{mary.id}/temporary-password", json={"password": TEMP})
    assert r.status_code == 204
    assert old.get("/api/me").status_code == 401, "the reset signs her out everywhere"

    c = sign_in("mary@example.org", TEMP)
    assert c.get("/api/me").json()["must_change_password"] is True
    blocked = c.get("/api/users")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "password_change_required"
    changed = c.post(
        "/api/me/password", json={"current_password": TEMP, "new_password": MINE}
    )
    assert changed.status_code == 204
    assert c.get("/api/me").json()["must_change_password"] is False


def test_changing_your_password_signs_out_your_other_sessions(session):
    owner(session)
    here = sign_in("owner@example.org")
    there = sign_in("owner@example.org")
    r = here.post(
        "/api/me/password", json={"current_password": PASSWORD, "new_password": MINE}
    )
    assert r.status_code == 204
    assert there.get("/api/me").status_code == 401
    assert here.get("/api/me").status_code == 200


def test_the_current_password_must_be_right(session):
    owner(session)
    r = sign_in("owner@example.org").post(
        "/api/me/password", json={"current_password": "x" * 12, "new_password": MINE}
    )
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "current_password"


def test_the_owner_changes_roles_but_never_leaves_the_archive_without_an_owner(
    session,
):
    me = owner(session)
    mary = member(session, Role.VIEWER, "mary@example.org")
    o = sign_in("owner@example.org")
    r = o.patch(f"/api/users/{mary.id}", json={"role": "owner", "is_executor": True})
    assert (r.json()["role"], r.json()["is_executor"]) == ("owner", True)
    assert o.patch(f"/api/users/{me.id}", json={"role": "viewer"}).status_code == 200
    last = sign_in("mary@example.org").patch(
        f"/api/users/{mary.id}", json={"role": "contributor"}
    )
    assert last.status_code == 409
    assert last.json()["error"]["code"] == "last_owner"


def test_removing_a_member_signs_them_out_and_keeps_them_out(session):
    owner(session)
    mary = member(session, Role.CONTRIBUTOR, "mary@example.org")
    theirs = sign_in("mary@example.org")
    o = sign_in("owner@example.org")
    assert o.delete(f"/api/users/{mary.id}").status_code == 204
    assert theirs.get("/api/me").status_code == 401
    r = make_client().post(
        "/api/auth/login", json={"email": "mary@example.org", "password": PASSWORD}
    )
    assert r.status_code == 401
    assert [u["email"] for u in o.get("/api/users").json()] == ["owner@example.org"]


def test_the_owner_cannot_remove_themselves(session):
    me = owner(session)
    assert sign_in("owner@example.org").delete(f"/api/users/{me.id}").status_code == 409


def test_my_sessions_lists_the_live_ones_and_marks_this_one(session):
    owner(session)
    sign_in("owner@example.org")
    c = sign_in("owner@example.org")
    listed = c.get("/api/me/sessions").json()
    assert len(listed) == 2
    assert [s["current"] for s in listed].count(True) == 1
