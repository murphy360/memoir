from tests.accounts import PASSWORD, owner, sign_in
from tests.conftest import make_client


def test_a_change_from_another_origin_is_refused(session):
    owner(session)
    c = make_client()
    r = c.post(
        "/api/auth/login",
        json={"email": "owner@example.org", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_a_change_with_no_origin_and_no_referer_is_refused(session):
    owner(session)
    c = make_client()
    del c.headers["Origin"]
    r = c.post("/api/auth/login", json={"email": "owner@example.org", "password": "x"})
    assert r.status_code == 403


def test_the_referer_stands_in_for_a_missing_origin(session):
    owner(session)
    c = make_client()
    del c.headers["Origin"]
    r = c.post(
        "/api/auth/login",
        json={"email": "owner@example.org", "password": PASSWORD},
        headers={"Referer": "https://testserver/memoir/login"},
    )
    assert r.status_code == 200


def test_a_signed_in_change_needs_the_session_csrf_token(session):
    owner(session)
    c = sign_in("owner@example.org")
    token = c.headers.pop("X-CSRF-Token")
    missing = c.patch("/api/me", json={"display_name": "Corey"})
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "csrf_failed"
    wrong = c.patch(
        "/api/me", json={"display_name": "Corey"}, headers={"X-CSRF-Token": "x"}
    )
    assert wrong.status_code == 403
    right = c.patch(
        "/api/me", json={"display_name": "Corey"}, headers={"X-CSRF-Token": token}
    )
    assert right.status_code == 200


def test_reading_needs_no_token(session):
    owner(session)
    c = sign_in("owner@example.org")
    del c.headers["X-CSRF-Token"]
    assert c.get("/api/me").status_code == 200
