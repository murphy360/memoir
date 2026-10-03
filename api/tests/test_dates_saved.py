"""How dates are read when saved, previewed, and protected from jobs."""

from datetime import date

from app.accounts.models import Role
from app.dates.store import set_by_job
from app.domain.events import Event
from tests.accounts import member, sign_in
from tests.domain import event, family, made, memory, period, person


def test_the_preview_says_what_it_read(session):
    c = family(session)
    ok = made(c.post("/api/dates/parse", json={"text": "summer 1968"}), 200)
    assert ok == {
        "ok": True,
        "start": "1968-06-01",
        "end": "1968-08-31",
        "precision": "approximate",
        "reading": "Summer 1968",
        "message": None,
        "examples": [],
    }
    bad = made(c.post("/api/dates/parse", json={"text": "when I was little"}), 200)
    assert bad["ok"] is False
    assert bad["message"] == "Could not read this date."
    assert "July 16, 1968" in bad["examples"]


def test_a_viewer_may_preview(session):
    family(session)
    member(session, Role.VIEWER)
    r = sign_in("viewer@example.org").post("/api/dates/parse", json={"text": "1968"})
    assert r.status_code == 200


def test_an_event_date_is_read_when_saved(session):
    c = family(session)
    ev = event(c, "Wedding", date_text="June 14, 2008")
    assert (ev["date_start"], ev["date_end"], ev["date_precision"]) == (
        "2008-06-14",
        "2008-06-14",
        "day",
    )
    assert session.get(Event, ev["id"]).date_source == "manual"
    changed = made(
        c.patch(f"/api/events/{ev['id']}", json={"date_text": "June 2008"}), 200
    )
    assert (changed["date_start"], changed["date_end"]) == ("2008-06-01", "2008-06-30")


def test_an_unreadable_date_is_refused_unless_kept_as_text(session):
    c = family(session)
    r = c.post("/api/events", json={"title": "Prom", "date_text": "senior year"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unreadable_date"
    assert r.json()["error"]["field"] == "date_text"
    assert "Try one like" in r.json()["error"]["message"]
    kept = event(c, "Prom", date_text="senior year", keep_text_only=True)
    assert (kept["date_text"], kept["date_start"], kept["date_precision"]) == (
        "senior year",
        None,
        None,
    )


def test_clearing_a_date_clears_its_reading(session):
    c = family(session)
    ev = event(c, "Prom", date_text="1985")
    cleared = made(c.patch(f"/api/events/{ev['id']}", json={"date_text": None}), 200)
    assert (cleared["date_text"], cleared["date_start"]) == (None, None)
    assert session.get(Event, ev["id"]).date_source is None


def test_a_period_can_run_to_now_and_reversed_ends_are_put_right(session):
    c = family(session)
    corey = person(c, "Corey")
    retired = period(c, corey["id"], "Retirement", start_text="2015", end_text="now")
    assert (retired["start_on"], retired["end_on"]) == (
        "2015-01-01",
        date.today().isoformat(),
    )
    flipped = period(c, corey["id"], "Navy", start_text="2002", end_text="1998")
    assert (flipped["start_on"], flipped["end_on"]) == ("1998-01-01", "2002-12-31")
    only_end = made(
        c.patch(f"/api/periods/{flipped['id']}", json={"end_text": "2005"}), 200
    )
    assert (only_end["start_text"], only_end["end_on"]) == ("2002", "2005-12-31")


def test_epics_people_memories_and_assets_read_their_dates(session):
    from tests.test_merge import asset, blob

    c = family(session)
    corey = person(c, "Corey", birth_text="March 3, 1975")
    assert corey["birth_start"] == "1975-03-03"
    navy = period(c, corey["id"], "Navy")
    ep = made(
        c.post(
            "/api/epics",
            json={
                "period_id": navy["id"],
                "title": "Norfolk",
                "start_text": "the early 1990s",
            },
        )
    )
    assert ep["start_on"] == "1990-01-01"
    m = memory(c, title="Erie", date_text="summer of 1968")
    assert (m["date_start"], m["date_precision"]) == ("1968-06-01", "approximate")
    a = asset(c, blob(session))
    dated = made(
        c.patch(f"/api/assets/{a['id']}", json={"capture_text": "4/10/2026"}), 200
    )
    assert dated["capture_start"] == "2026-04-10"


def test_a_job_never_overwrites_a_date_a_person_set(session):
    c = family(session)
    typed = event(c, "Wedding", date_text="June 14, 2008")
    row = session.get(Event, typed["id"])
    assert set_by_job(row, "date", "2009", "transcript") is False
    assert row.date_text == "June 14, 2008"

    loose = Event(archive_id=row.archive_id, title="Loose", weight=5)
    session.add(loose)
    session.flush()
    assert set_by_job(loose, "date", "summer 1968", "transcript") is True
    assert (loose.date_start, loose.date_source) == (date(1968, 6, 1), "transcript")
    assert set_by_job(loose, "date", "1969", "research") is True
    assert loose.date_text == "1969"


def test_events_sort_by_their_read_dates(session):
    c = family(session)
    for title, when in (("Later", "1990"), ("Undated", None), ("Earlier", "the 1960s")):
        event(c, title, **({"date_text": when} if when else {}))
    titles = [e["title"] for e in c.get("/api/events").json()["items"]]
    assert titles == ["Earlier", "Later", "Undated"]
