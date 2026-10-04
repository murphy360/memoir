"""Where memories go: the suggestion rule, auto-filing, placing, the inbox, the
timeline.
"""

import time
from datetime import date

import pytest

from app.accounts.models import User
from app.domain.events import Event
from app.domain.memories import Memory
from app.domain.periods import Period
from app.jobs.registry import JobContext
from app.placement import service
from app.placement.suggest import gap, suggest
from tests.domain import event, family, made, memory, period, person, place, timeline


def me(session):
    return session.query(User).one()


def quick(c, session, date_text, title="A memory", storyteller_id=None):
    """A memory as a quick recording leaves it, with its date read."""
    m = memory(c, title=title, date_text=date_text, storyteller_id=storyteller_id)
    row = session.get(Memory, m["id"])
    row.capture_context = {"quick": True}
    session.commit()
    return row


def test_gap_between_ranges():
    assert gap(date(1968, 6, 1), date(1968, 8, 31), date(1968, 7, 4), None).days == 0
    assert (
        gap(
            date(1968, 6, 1), date(1968, 6, 30), date(1968, 7, 10), date(1968, 7, 12)
        ).days
        == 10
    )
    assert gap(date(1968, 6, 1), date(1968, 6, 30), None, None) is None


@pytest.fixture
def life(session):
    """Corey's life: the 1960s and a narrower Erie years period, a few events."""
    c = family(session)
    corey = person(c, "Corey", user_id=me(session).id)
    sixties = period(c, corey["id"], "The sixties", start_text="1960", end_text="1969")
    erie = period(c, corey["id"], "Erie years", start_text="1967", end_text="1970")
    w = {"c": c, "corey": corey, "sixties": sixties, "erie": erie}
    for title, when, weight in (
        ("Summer job", "summer 1968", 5),
        ("Fair week", "August 1968", 8),
        ("Graduation", "June 1969", 5),
    ):
        ev = event(c, title, date_text=when, weight=weight)
        place(c, ev["id"], corey["id"], period_id=erie["id"])
        w[title] = ev
    return w


def first(session, memory_row, person_id):
    return suggest(session, memory_row, person_id)[0]


def test_the_closest_event_in_the_narrowest_covering_period_wins(session, life):
    m = quick(life["c"], session, "July 1968")
    best = first(session, m, life["corey"]["id"])
    assert (best.kind, best.period_id) == ("event", life["erie"]["id"])
    assert best.event_id in (life["Summer job"]["id"], life["Fair week"]["id"])
    assert best.label.startswith("Erie years, ")


def test_a_heavier_event_wins_a_tie(session, life):
    m = quick(life["c"], session, "August 1968")
    assert first(session, m, life["corey"]["id"]).event_id == life["Fair week"]["id"]


def test_far_from_any_event_it_is_a_new_event_in_the_period(session, life):
    m = quick(life["c"], session, "1962")
    best = first(session, m, life["corey"]["id"])
    assert (best.kind, best.period_id) == ("period", life["sixties"]["id"])


def test_nothing_covers_the_dates_so_something_new_for_the_decade(session, life):
    m = quick(life["c"], session, "1985")
    options = suggest(session, m, life["corey"]["id"])
    assert [(o.kind, o.decade) for o in options] == [("new", 1980)]
    assert options[0].label == "The 1980s, a new event"


def test_a_mentioned_persons_event_is_offered_too(session, life):
    c = life["c"]
    mary = person(c, "Mary")
    hers = period(c, mary["id"], "Mary in Erie", start_text="1960", end_text="1990")
    move = event(c, "Move to Erie", date_text="1985")
    place(c, move["id"], mary["id"], period_id=hers["id"])
    m = memory(c, date_text="1985", mentioned_ids=[mary["id"]])
    options = suggest(session, session.get(Memory, m["id"]), life["corey"]["id"])
    assert any(
        o.event_id == move["id"] and o.label == "Mary's Move to Erie" for o in options
    )


def test_an_undated_memory_has_no_suggestion(session, life):
    m = memory(life["c"], title="Sometime")
    assert suggest(session, session.get(Memory, m["id"]), life["corey"]["id"]) == []


def test_a_quick_memory_is_filed_and_says_where(session, life):
    m = quick(life["c"], session, "August 1968", title="Corn dogs at the fair")
    assert service.autofile(session, m) is True
    shown = made(life["c"].get(f"/api/memories/{m.id}/placement"), 200)
    assert shown["saved_to"] == {
        "event_id": life["Fair week"]["id"],
        "event_title": "Fair week",
        "period_id": life["erie"]["id"],
        "period_title": "Erie years",
        "created_for_this_memory": False,
    }


def test_a_memory_dated_where_nothing_is_gets_its_decade_labelled(session, life):
    m = quick(life["c"], session, "summer 1985", title="The lake house")
    service.autofile(session, m)
    where = service.saved_to(session, m)
    assert (where.period_title, where.event_title, where.created_for_this_memory) == (
        "The 1980s",
        "The lake house",
        True,
    )
    p = session.get(Period, where.period_id)
    assert (p.start_on, p.end_on, p.auto_created_for_memory_id) == (
        date(1980, 1, 1),
        date(1989, 12, 31),
        m.id,
    )
    assert session.get(Event, where.event_id).date_start == date(1985, 6, 1)


def test_auto_filing_respects_the_setting_and_only_quick_memories(session, life):
    c = life["c"]
    typed = memory(c, title="Typed", date_text="August 1968")
    assert service.autofile(session, session.get(Memory, typed["id"])) is False
    c.patch("/api/settings", json={"auto_file_quick_memories": False})
    m = quick(c, session, "August 1968")
    assert service.autofile(session, m) is False
    assert m.event_id is None


def test_a_deleted_auto_event_is_never_made_again(session, life):
    c = life["c"]
    m = quick(c, session, "1985", title="Lake house")
    service.autofile(session, m)
    made_event = m.event_id
    c.delete(f"/api/events/{made_event}")
    from app.analysis.extract import autofile

    assert autofile(session, m) is False, "a memory is filed once"
    inbox = made(c.get("/api/inbox"), 200)["items"]
    assert [i["memory"]["id"] for i in inbox] == [m.id]
    again = quick(c, session, "1985", title="Lake house again")
    service.autofile(session, again)
    assert again.event_id != made_event


def test_changing_where_a_memory_is_moves_it(session, life):
    c = life["c"]
    m = quick(c, session, "August 1968")
    service.autofile(session, m)
    moved = made(
        c.post(
            f"/api/memories/{m.id}/place", json={"event_id": life["Summer job"]["id"]}
        ),
        200,
    )
    assert moved["saved_to"]["event_title"] == "Summer job"
    assert moved["memory"]["event_id"] == life["Summer job"]["id"]


def test_placing_somewhere_new(session, life):
    c = life["c"]
    m = memory(c, title="Basic training", date_text="1990")
    placed = made(
        c.post(
            f"/api/memories/{m['id']}/place",
            json={
                "new_period": {
                    "title": "Navy years",
                    "start_text": "1990",
                    "end_text": "1994",
                },
                "title": "Basic training at Great Lakes",
                "date_text": "spring 1990",
            },
        ),
        200,
    )
    where = placed["saved_to"]
    assert (
        where["period_title"],
        where["event_title"],
        where["created_for_this_memory"],
    ) == (
        "Navy years",
        "Basic training at Great Lakes",
        False,
    )
    entries = {e["title"]: e for e in timeline(c, life["corey"]["id"])}
    assert entries["Basic training at Great Lakes"]["date_start"] == "1990-03-01"


def test_somewhere_new_reuses_a_period_of_the_same_name(session, life):
    c = life["c"]
    body = {
        "new_period": {
            "title": "the sixties",
            "start_text": "1960",
            "end_text": "1969",
        },
        "title": "Fishing",
    }
    one = memory(c, title="One")
    two = memory(c, title="Two")
    a = made(c.post(f"/api/memories/{one['id']}/place", json=body), 200)["saved_to"]
    b = made(c.post(f"/api/memories/{two['id']}/place", json=body), 200)["saved_to"]
    assert a["period_id"] == b["period_id"] == life["sixties"]["id"]


def test_placing_needs_somewhere(session, life):
    m = memory(life["c"], title="x")
    assert life["c"].post(f"/api/memories/{m['id']}/place", json={}).status_code == 422


def test_the_inbox_offers_each_memory_its_suggestion_and_empties_as_they_are_placed(
    session, life
):
    c = life["c"]
    dated = memory(c, title="Fair", date_text="August 1968")
    undated = memory(c, title="Sometime")
    items = made(c.get("/api/inbox"), 200)["items"]
    by_title = {i["memory"]["title"]: i["suggestion"] for i in items}
    assert by_title["Fair"]["event_id"] == life["Fair week"]["id"]
    assert by_title["Sometime"] is None
    accepted = made(c.post(f"/api/inbox/{dated['id']}/accept"), 200)
    assert accepted["saved_to"]["event_title"] == "Fair week"
    assert c.post(f"/api/inbox/{undated['id']}/accept").status_code == 409
    assert [i["memory"]["title"] for i in made(c.get("/api/inbox"), 200)["items"]] == [
        "Sometime"
    ]


def test_a_user_gets_their_own_person_for_a_timeline(session):
    c = family(session)
    mine = made(c.get("/api/me/person"), 200)
    assert mine["name"] == "Owner" and mine["user_id"] == me(session).id
    assert made(c.get("/api/me/person"), 200)["id"] == mine["id"]


def test_a_timeline_of_200_events_comes_by_period_quickly(session):
    c = family(session)
    corey = person(c, "Corey")
    periods = [
        period(c, corey["id"], f"Decade {d}", start_text=str(d), end_text=str(d + 9))
        for d in range(1950, 2030, 10)
    ]
    for n in range(200):
        p = periods[n % len(periods)]
        ev = event(c, f"Event {n}", date_text=str(int(p["title"][-4:]) + n % 10))
        place(c, ev["id"], corey["id"], period_id=p["id"])
    started = time.monotonic()
    t = made(c.get(f"/api/people/{corey['id']}/timeline"), 200)
    first_period = made(
        c.get(
            f"/api/people/{corey['id']}/events", params={"period_id": periods[0]["id"]}
        ),
        200,
    )
    elapsed = time.monotonic() - started
    assert [p["event_count"] for p in t["periods"]] == [25] * 8
    assert [p["title"] for p in t["periods"]][:2] == ["Decade 1950", "Decade 1960"]
    assert len(first_period["items"]) == 25
    assert elapsed < 1.0, elapsed


def test_extraction_files_a_quick_memory(session, life):
    from app.ai import registry
    from app.ai.fake import FakeAI
    from app.analysis.extract import extract

    fake = FakeAI()
    fake.data = {
        "title": "Corn dogs at the fair",
        "description": "x",
        "date_text": "August 1968",
        "date_precision": "month",
        "storyteller_name": "",
        "people": [],
        "places": [],
        "tone": "positive",
    }
    registry.use(fake)
    try:
        m = memory(life["c"], transcript="We had corn dogs at the fair in August 1968.")
        row = session.get(Memory, m["id"])
        row.capture_context = {"quick": True}
        session.commit()
        extract(JobContext(session, 0), {"memory_id": m["id"]})
        session.refresh(row)
        assert row.event_id == life["Fair week"]["id"]
    finally:
        registry.reset()
