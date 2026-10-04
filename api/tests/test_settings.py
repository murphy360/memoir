from app.accounts.models import Role
from tests.accounts import member, sign_in
from tests.domain import family, made


def test_settings_have_defaults_and_the_owner_changes_them(session):
    c = family(session)
    s = made(c.get("/api/settings"), 200)
    assert (s["archive_name"], s["face_auto_assign_threshold"], s["ai_research"]) == (
        "The Murphys",
        0.92,
        True,
    )
    changed = made(
        c.patch(
            "/api/settings",
            json={
                "storyteller_name": "Grandma",
                "ai_research": False,
                "time_zone": "America/New_York",
            },
        ),
        200,
    )
    assert (
        changed["storyteller_name"],
        changed["ai_research"],
        changed["time_zone"],
    ) == (
        "Grandma",
        False,
        "America/New_York",
    )


def test_a_bad_time_zone_is_refused(session):
    c = family(session)
    r = c.patch("/api/settings", json={"time_zone": "Mars/Olympus"})
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "time_zone"


def test_a_contributor_reads_but_does_not_change_settings(session):
    family(session)
    member(session, Role.CONTRIBUTOR)
    c = sign_in("contributor@example.org")
    assert c.get("/api/settings").status_code == 200
    assert c.patch("/api/settings", json={"ai_research": False}).status_code == 403
