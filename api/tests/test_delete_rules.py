"""Every foreign key's delete rule, checked in the database itself (requirements 3.2).

Each test builds a small world through the API, removes one row for good with SQL (as a
purge would), and checks what the database did to the rows that pointed at it.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.domain import epic, event, family, made, memory, period, person, place
from tests.test_merge import asset, blob


@pytest.fixture
def world(session):
    c = family(session)
    w = {"c": c}
    w["thread"] = made(c.post("/api/threads", json={"title": "Farm"}))
    w["place"] = made(c.post("/api/places", json={"name": "Erie"}))
    w["corey"], w["jane"] = person(c, "Corey"), person(c, "Jane")
    c.post(f"/api/people/{w['corey']['id']}/aliases", json={"alias": "Dad"})
    w["period"] = period(c, w["corey"]["id"], "Navy")
    w["epic"] = epic(c, w["period"]["id"], "Norfolk", thread_id=w["thread"]["id"])
    w["event"] = event(
        c, "Leave", place_id=w["place"]["id"], thread_id=w["thread"]["id"]
    )
    place(c, w["event"]["id"], w["corey"]["id"], epic_id=w["epic"]["id"])
    place(c, w["event"]["id"], w["jane"]["id"])
    w["sha"] = blob(session)
    w["asset"] = asset(c, w["sha"])
    c.patch(f"/api/assets/{w['asset']['id']}", json={"place_id": w["place"]["id"]})
    c.put(f"/api/events/{w['event']['id']}/assets/{w['asset']['id']}", json={})
    w["memory"] = memory(
        c,
        event_id=w["event"]["id"],
        storyteller_id=w["corey"]["id"],
        mentioned_ids=[w["jane"]["id"]],
        place_ids=[w["place"]["id"]],
    )
    w["question"] = made(
        c.post(
            "/api/questions",
            json={"text": "Who drove?", "scope": "event", "event_id": w["event"]["id"]},
        )
    )
    return w


def run(engine, sql: str, **params):
    with engine.begin() as conn:
        conn.execute(text(sql), params)


def value(engine, sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def test_a_kept_file_cannot_be_removed_while_an_asset_uses_it(world, engine):
    with pytest.raises(IntegrityError):
        run(engine, "DELETE FROM blobs WHERE sha256 = :s", s=world["sha"])


def test_removing_an_event_takes_its_links_and_frees_its_memories(world, engine):
    run(engine, "DELETE FROM events WHERE id = :i", i=world["event"]["id"])
    assert value(engine, "SELECT count(*) FROM participants") == 0
    assert value(engine, "SELECT count(*) FROM event_assets") == 0
    assert value(engine, "SELECT event_id FROM memories") is None
    assert value(engine, "SELECT event_id FROM questions") is None
    assert value(engine, "SELECT count(*) FROM assets") == 1


def test_removing_a_person_takes_their_life_and_leaves_others(world, engine):
    corey = world["corey"]["id"]
    run(engine, "DELETE FROM people WHERE id = :i", i=corey)
    assert value(engine, "SELECT count(*) FROM person_aliases") == 0
    assert value(engine, "SELECT count(*) FROM periods") == 0
    assert value(engine, "SELECT count(*) FROM epics") == 0
    assert value(engine, "SELECT count(*) FROM participants") == 1
    assert value(engine, "SELECT storyteller_id FROM memories") is None
    assert value(engine, "SELECT count(*) FROM memory_mentions") == 1


def test_a_period_or_epic_with_placements_cannot_vanish_under_them(world, engine):
    for sql, i in (
        ("DELETE FROM epics WHERE id = :i", world["epic"]["id"]),
        ("DELETE FROM periods WHERE id = :i", world["period"]["id"]),
    ):
        with pytest.raises(IntegrityError):
            run(engine, sql, i=i)


def test_once_unplaced_a_period_goes_with_its_epics(world, engine):
    run(engine, "UPDATE participants SET period_id = NULL, epic_id = NULL")
    run(engine, "DELETE FROM periods WHERE id = :i", i=world["period"]["id"])
    assert value(engine, "SELECT count(*) FROM epics") == 0


def test_removing_a_thread_untags(world, engine):
    run(engine, "DELETE FROM threads WHERE id = :i", i=world["thread"]["id"])
    assert value(engine, "SELECT thread_id FROM epics") is None
    assert value(engine, "SELECT thread_id FROM events") is None


def test_removing_a_place_unlinks_it_everywhere(world, engine):
    run(engine, "DELETE FROM places WHERE id = :i", i=world["place"]["id"])
    assert value(engine, "SELECT place_id FROM events") is None
    assert value(engine, "SELECT place_id FROM assets") is None
    assert value(engine, "SELECT count(*) FROM memory_places") == 0


def test_removing_a_memory_takes_its_mentions_and_frees_questions(world, engine):
    run(engine, "UPDATE questions SET source_memory_id = :m", m=world["memory"]["id"])
    run(engine, "DELETE FROM memories WHERE id = :i", i=world["memory"]["id"])
    assert value(engine, "SELECT count(*) FROM memory_mentions") == 0
    assert value(engine, "SELECT count(*) FROM memory_places") == 0
    assert value(engine, "SELECT source_memory_id FROM questions") is None


def test_removing_an_asset_takes_its_links(world, engine):
    run(engine, "DELETE FROM assets WHERE id = :i", i=world["asset"]["id"])
    assert value(engine, "SELECT count(*) FROM event_assets") == 0


def test_removing_a_login_keeps_what_they_made(world, engine, session):
    from app.accounts.models import Role
    from tests.accounts import member

    removed = member(session, Role.VIEWER, "gone@example.org")
    run(
        engine,
        "UPDATE people SET user_id = :u WHERE id = :p",
        u=removed.id,
        p=world["jane"]["id"],
    )
    run(engine, "UPDATE events SET created_by = :u", u=removed.id)
    run(engine, "DELETE FROM users WHERE id = :u", u=removed.id)
    assert (
        value(engine, "SELECT user_id FROM people WHERE id = :p", p=world["jane"]["id"])
        is None
    )
    assert value(engine, "SELECT created_by FROM events") is None


def test_removing_the_archive_removes_everything_in_it(world, engine):
    run(engine, "DELETE FROM audit_events")
    run(engine, "UPDATE archives SET created_by = NULL, updated_by = NULL")
    run(engine, "DELETE FROM sessions")
    run(engine, "DELETE FROM users")
    run(engine, "DELETE FROM archives")
    for table in (
        "people",
        "periods",
        "events",
        "memories",
        "assets",
        "questions",
        "threads",
    ):
        assert value(engine, f"SELECT count(*) FROM {table}") == 0, table
