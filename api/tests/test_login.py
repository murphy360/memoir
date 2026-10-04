from datetime import timedelta

from sqlalchemy import select, update

from app.accounts.models import Role, UserSession
from app.core.db import utcnow
from tests.accounts import PASSWORD, member, owner, sign_in

GENERIC = "That email and password do not match an account."


def test_sign_in_sets_a_secure_httponly_session_cookie(client, session):
    owner(session)
    response = client.post(
        "/api/auth/login", json={"email": "OWNER@example.org", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "owner"
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("memoir_session="))
    for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Max-Age=2592000"):
        assert attribute in session_cookie
    csrf_cookie = next(c for c in cookies if c.startswith("memoir_csrf="))
    assert "HttpOnly" not in csrf_cookie
    assert client.get("/api/me").json()["email"] == "owner@example.org"


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(client, session):
    owner(session)
    wrong = client.post(
        "/api/auth/login", json={"email": "owner@example.org", "password": "nope" * 4}
    )
    unknown = client.post(
        "/api/auth/login", json={"email": "who@example.org", "password": PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"]["message"] == GENERIC


def test_six_failures_from_one_address_in_a_minute_are_refused(client, session):
    owner(session)
    for _ in range(5):
        r = client.post(
            "/api/auth/login", json={"email": "owner@example.org", "password": "x" * 12}
        )
        assert r.status_code == 401
    sixth = client.post(
        "/api/auth/login", json={"email": "owner@example.org", "password": PASSWORD}
    )
    assert sixth.status_code == 401
    assert sixth.json()["error"]["message"] == GENERIC


def test_too_many_failures_on_one_account_from_many_addresses_are_refused(
    session, settings
):
    from app.accounts import ratelimit

    owner(session)
    for n in range(settings.login_account_limit):
        ratelimit.note(session, f"10.0.0.{n}", "owner@example.org", False)
    session.commit()
    assert ratelimit.blocked(session, "10.9.9.9", "owner@example.org", settings)
    assert not ratelimit.blocked(session, "10.9.9.9", "other@example.org", settings)


def test_a_removed_user_cannot_sign_in(client, session):
    user = member(session, Role.CONTRIBUTOR)
    user.deleted_at = utcnow()
    session.commit()
    r = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert r.status_code == 401


def test_a_session_idle_for_thirty_days_ends(session):
    owner(session)
    c = sign_in("owner@example.org")
    session.execute(
        update(UserSession).values(last_seen_at=utcnow() - timedelta(days=31))
    )
    session.commit()
    assert c.get("/api/me").status_code == 401


def test_activity_keeps_a_session_alive_and_renews_the_cookie(session):
    owner(session)
    c = sign_in("owner@example.org")
    session.execute(
        update(UserSession).values(last_seen_at=utcnow() - timedelta(days=29))
    )
    session.commit()
    response = c.get("/api/me")
    assert response.status_code == 200
    assert any(
        h.startswith("memoir_session=") for h in response.headers.get_list("set-cookie")
    )
    row = session.scalars(select(UserSession)).one()
    session.refresh(row)
    assert utcnow() - row.last_seen_at < timedelta(minutes=1)


def test_sign_out_ends_the_session(session):
    owner(session)
    c = sign_in("owner@example.org")
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/me").status_code == 401


def test_sign_out_everywhere_ends_every_other_session_at_once(session):
    owner(session)
    laptop = sign_in("owner@example.org")
    phone = sign_in("owner@example.org")
    assert laptop.post("/api/auth/logout-all").status_code == 204
    assert phone.get("/api/me").status_code == 401
    assert laptop.get("/api/me").status_code == 200
