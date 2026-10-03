"""Soft deletion hides; purging removes for good, after 30 days or on the
owner's word.
"""

from datetime import timedelta

from sqlalchemy import select, text, update

from app.core.db import utcnow
from app.domain.events import Event
from app.domain.participants import Participant
from app.domain.people import Person
from app.domain.periods import Period
from tests.domain import epic, event, family, made, memory, period, person, place


def test_purge_keeps_the_last_thirty_days(session):
    c = family(session)
    old, recent = event(c, "Old"), event(c, "Recent")
    c.delete(f"/api/events/{old['id']}")
    c.delete(f"/api/events/{recent['id']}")
    session.execute(
        update(Event)
        .where(Event.id == old["id"])
        .values(deleted_at=utcnow() - timedelta(days=31))
    )
    session.commit()
    counts = made(c.post("/api/trash/purge"), 200)["counts"]
    assert counts["events"] == 1
    remaining = session.scalars(select(Event.id)).all()
    assert remaining == [recent["id"]]


def test_purging_a_period_unplaces_events_first(session):
    c = family(session)
    corey = person(c, "Corey")
    navy, school = period(c, corey["id"], "Navy"), period(c, corey["id"], "School")
    ep = epic(c, navy["id"], "Norfolk")
    ev = event(c, "Shore leave")
    place(c, ev["id"], corey["id"], epic_id=ep["id"])
    session.execute(
        text("UPDATE periods SET deleted_at = now() WHERE id = :i"), {"i": navy["id"]}
    )
    session.commit()
    made(c.post("/api/trash/purge", params={"older_than_days": 0}), 200)
    row = session.scalars(select(Participant)).one()
    assert (row.period_id, row.epic_id) == (None, None)
    assert session.scalars(select(Period.id)).all() == [school["id"]]


def test_purging_a_person_removes_their_periods_and_participation_only(session):
    c = family(session)
    corey, jane = person(c, "Corey"), person(c, "Jane")
    navy = period(c, corey["id"], "Navy")
    ev = event(c, "Wedding")
    place(c, ev["id"], corey["id"], period_id=navy["id"])
    place(c, ev["id"], jane["id"])
    m = memory(c, storyteller_id=corey["id"], event_id=ev["id"])
    c.delete(f"/api/people/{corey['id']}")
    made(c.post("/api/trash/purge", params={"older_than_days": 0}), 200)
    assert session.scalars(select(Person.id)).all() == [jane["id"]]
    assert session.scalars(select(Period.id)).all() == []
    people = c.get(f"/api/events/{ev['id']}").json()["participants"]
    assert [p["name"] for p in people] == ["Jane"]
    assert c.get(f"/api/memories/{m['id']}").json()["storyteller_id"] is None


def test_the_purge_job_runs_across_archives(session):
    from app.jobs.registry import HANDLERS, JobContext

    c = family(session)
    old = event(c, "Old")
    c.delete(f"/api/events/{old['id']}")
    result = HANDLERS["domain.purge"](JobContext(session, 0), {"days": 0})
    assert result["events"] == 1
