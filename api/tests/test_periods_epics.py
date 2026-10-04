"""Periods and epics: slugs, moves, and deleting with what is inside
(requirements 3.2).
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.domain import epic, event, family, made, period, person, place, timeline


def test_slugs_are_unique_per_person(session):
    c = family(session)
    corey, jane = person(c, "Corey"), person(c, "Jane")
    a = period(c, corey["id"], "Childhood")
    b = period(c, corey["id"], "Childhood")
    other = period(c, jane["id"], "Childhood")
    assert (a["slug"], b["slug"], other["slug"]) == (
        "childhood",
        "childhood-2",
        "childhood",
    )


def test_a_period_with_contents_is_not_deleted_without_a_choice(session):
    c = family(session)
    corey = person(c, "Corey")
    navy = period(c, corey["id"], "Navy")
    epic(c, navy["id"], "Norfolk")
    r = c.delete(f"/api/periods/{navy['id']}")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "period_has_children"
    assert c.get(f"/api/periods/{navy['id']}").status_code == 200


def test_an_empty_period_is_simply_deleted(session):
    c = family(session)
    empty = period(c, person(c, "Corey")["id"], "Empty")
    assert made(c.delete(f"/api/periods/{empty['id']}"), 200)["epics_moved"] == 0


def test_deleting_a_period_can_move_its_epics_and_events(session):
    c = family(session)
    corey = person(c, "Corey")
    navy, service = period(c, corey["id"], "Navy"), period(c, corey["id"], "Service")
    norfolk = epic(c, navy["id"], "Norfolk")
    ev, ev2 = event(c, "Shore leave"), event(c, "Boot camp")
    place(c, ev["id"], corey["id"], epic_id=norfolk["id"])
    place(c, ev2["id"], corey["id"], period_id=navy["id"])

    done = made(
        c.delete(
            f"/api/periods/{navy['id']}",
            params={"children": "move", "move_to": service["id"]},
        ),
        200,
    )
    assert done == {
        "epics_moved": 1,
        "epics_removed": 0,
        "placements_moved": 2,
        "placements_unassigned": 0,
    }
    assert c.get(f"/api/epics/{norfolk['id']}").json()["period_id"] == service["id"]
    assert {e["period_id"] for e in timeline(c, corey["id"])} == {service["id"]}


def test_deleting_a_period_can_unassign_its_events(session):
    c = family(session)
    corey = person(c, "Corey")
    navy = period(c, corey["id"], "Navy")
    norfolk = epic(c, navy["id"], "Norfolk")
    ev = event(c, "Shore leave")
    place(c, ev["id"], corey["id"], epic_id=norfolk["id"])
    done = made(
        c.delete(f"/api/periods/{navy['id']}", params={"children": "unassign"}), 200
    )
    assert (done["epics_removed"], done["placements_unassigned"]) == (1, 1)
    [entry] = timeline(c, corey["id"])
    assert (entry["period_id"], entry["epic_id"]) == (None, None)
    assert c.get(f"/api/epics/{norfolk['id']}").status_code == 404


def test_moving_a_periods_contents_only_goes_to_the_same_person(session):
    c = family(session)
    corey, jane = person(c, "Corey"), person(c, "Jane")
    navy, hers = period(c, corey["id"], "Navy"), period(c, jane["id"], "Hers")
    epic(c, navy["id"], "Norfolk")
    r = c.delete(
        f"/api/periods/{navy['id']}", params={"children": "move", "move_to": hers["id"]}
    )
    assert r.status_code == 422


def test_moving_an_epic_moves_its_events(session):
    c = family(session)
    corey = person(c, "Corey")
    navy, later = period(c, corey["id"], "Navy"), period(c, corey["id"], "Later")
    norfolk = epic(c, navy["id"], "Norfolk")
    ev = event(c, "Shore leave")
    place(c, ev["id"], corey["id"], epic_id=norfolk["id"])
    moved = made(
        c.patch(f"/api/epics/{norfolk['id']}", json={"period_id": later["id"]}), 200
    )
    assert moved["period_id"] == later["id"]
    [entry] = timeline(c, corey["id"])
    assert (entry["period_id"], entry["epic_id"]) == (later["id"], norfolk["id"])


def test_an_epic_stays_in_one_persons_life(session):
    c = family(session)
    corey, jane = person(c, "Corey"), person(c, "Jane")
    navy, hers = period(c, corey["id"], "Navy"), period(c, jane["id"], "Hers")
    norfolk = epic(c, navy["id"], "Norfolk")
    r = c.patch(f"/api/epics/{norfolk['id']}", json={"period_id": hers["id"]})
    assert r.status_code == 422


def test_deleting_an_epic_leaves_its_events_in_the_period(session):
    c = family(session)
    corey = person(c, "Corey")
    navy = period(c, corey["id"], "Navy")
    norfolk = epic(c, navy["id"], "Norfolk")
    ev = event(c, "Shore leave")
    place(c, ev["id"], corey["id"], epic_id=norfolk["id"])
    assert c.delete(f"/api/epics/{norfolk['id']}").status_code == 204
    [entry] = timeline(c, corey["id"])
    assert (entry["period_id"], entry["epic_id"]) == (navy["id"], None)


def test_weight_is_one_to_ten(session, engine):
    c = family(session)
    navy = period(c, person(c, "Corey")["id"], "Navy")
    assert (
        c.post(
            "/api/epics", json={"period_id": navy["id"], "title": "x", "weight": 11}
        ).status_code
        == 422
    )
    assert c.post("/api/events", json={"title": "x", "weight": 0}).status_code == 422
    ev = event(c, "Fine", weight=10)
    with pytest.raises(IntegrityError, match="ck_events_weight_1_10"):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE events SET weight = 11 WHERE id = :i"), {"i": ev["id"]}
            )
