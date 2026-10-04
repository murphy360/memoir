"""Every person has a timeline; events tie them together (requirements 3.1, 3.2)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.domain import epic, event, family, memory, period, person, place, timeline


def test_one_event_sits_in_a_different_period_on_each_participant_timeline(session):
    c = family(session)
    corey, jane = person(c, "Corey"), person(c, "Jane")
    navy = period(c, corey["id"], "Navy years")
    ours = period(c, jane["id"], "Our marriage")
    wedding = event(c, "The wedding", date_text="June 2008")
    place(c, wedding["id"], corey["id"], period_id=navy["id"])
    assert [e["id"] for e in timeline(c, jane["id"])] == []

    place(c, wedding["id"], jane["id"], period_id=ours["id"])
    [on_corey] = timeline(c, corey["id"])
    [on_jane] = timeline(c, jane["id"])
    assert on_corey["id"] == on_jane["id"] == wedding["id"]
    assert (on_corey["period_id"], on_jane["period_id"]) == (navy["id"], ours["id"])
    assert len(c.get("/api/events").json()["items"]) == 1
    names = [p["name"] for p in on_jane["participants"]]
    assert names == ["Corey", "Jane"]


def test_a_placement_must_be_in_the_participants_own_period(session):
    c = family(session)
    corey, jane = person(c, "Corey"), person(c, "Jane")
    navy = period(c, corey["id"], "Navy years")
    wedding = event(c, "The wedding")
    r = c.put(
        f"/api/events/{wedding['id']}/participants/{jane['id']}",
        json={"period_id": navy["id"]},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "not_their_period"


def test_the_epic_decides_the_period(session):
    c = family(session)
    corey = person(c, "Corey")
    navy = period(c, corey["id"], "Navy years")
    norfolk = epic(c, navy["id"], "Norfolk")
    ev = event(c, "Shore leave")
    placed = place(c, ev["id"], corey["id"], epic_id=norfolk["id"])
    [me] = placed["participants"]
    assert (me["period_id"], me["epic_id"]) == (navy["id"], norfolk["id"])


def test_the_database_refuses_a_placement_in_someone_elses_period(session, engine):
    c = family(session)
    corey, jane = person(c, "Corey"), person(c, "Jane")
    navy = period(c, corey["id"], "Navy years")
    ev = event(c, "Shore leave")
    place(c, ev["id"], jane["id"])
    with pytest.raises(IntegrityError, match="fk_participants_own_period"):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE participants SET period_id = :p WHERE person_id = :j"),
                {"p": navy["id"], "j": jane["id"]},
            )


def test_the_database_refuses_an_epic_from_another_period(session, engine):
    c = family(session)
    corey = person(c, "Corey")
    navy, school = period(c, corey["id"], "Navy"), period(c, corey["id"], "School")
    norfolk = epic(c, navy["id"], "Norfolk")
    ev = event(c, "Prom")
    place(c, ev["id"], corey["id"], period_id=school["id"])
    with pytest.raises(IntegrityError, match="fk_participants_epic_in_period"):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE participants SET epic_id = :e"), {"e": norfolk["id"]}
            )


def test_a_memory_brings_its_storyteller_and_the_people_it_names(session):
    c = family(session)
    grandma, jim = person(c, "Grandma"), person(c, "Jim")
    ev = event(c, "The drive to Erie")
    memory(
        c,
        title="We drove to Erie",
        storyteller_id=grandma["id"],
        mentioned_ids=[jim["id"]],
        event_id=ev["id"],
    )
    people = c.get(f"/api/events/{ev['id']}").json()["participants"]
    assert [(p["name"], p["role"], p["source"], p["confirmed"]) for p in people] == [
        ("Grandma", "storyteller", "transcript", False),
        ("Jim", "mentioned", "transcript", False),
    ]
    confirmed = c.post(
        f"/api/events/{ev['id']}/participants/{jim['id']}/confirm"
    ).json()
    assert confirmed["participants"][1]["confirmed"] is True


def test_removing_a_participant_takes_the_event_off_their_timeline(session):
    c = family(session)
    corey = person(c, "Corey")
    ev = event(c, "Prom")
    place(c, ev["id"], corey["id"])
    assert len(timeline(c, corey["id"])) == 1
    assert (
        c.delete(f"/api/events/{ev['id']}/participants/{corey['id']}").status_code
        == 200
    )
    assert timeline(c, corey["id"]) == []


def test_an_event_nobody_placed_is_in_the_inbox(session):
    c = family(session)
    corey = person(c, "Corey")
    navy = period(c, corey["id"], "Navy")
    loose, placed = event(c, "Loose"), event(c, "Placed")
    place(c, placed["id"], corey["id"], period_id=navy["id"])
    place(c, loose["id"], corey["id"])
    inbox = c.get("/api/events", params={"unplaced": True}).json()["items"]
    assert [e["title"] for e in inbox] == ["Loose"]


def test_deleting_a_person_keeps_shared_events_on_everyone_elses_timeline(session):
    c = family(session)
    corey, jane = person(c, "Corey"), person(c, "Jane")
    navy, ours = period(c, corey["id"], "Navy"), period(c, jane["id"], "Ours")
    epic(c, navy["id"], "Norfolk")
    wedding = event(c, "The wedding")
    place(c, wedding["id"], corey["id"], period_id=navy["id"])
    place(c, wedding["id"], jane["id"], period_id=ours["id"])

    assert c.delete(f"/api/people/{corey['id']}").status_code == 204
    assert c.get(f"/api/people/{corey['id']}").status_code == 404
    assert c.get(f"/api/periods/{navy['id']}").status_code == 404
    assert c.get("/api/epics", params={"period_id": navy["id"]}).status_code == 404
    [still] = timeline(c, jane["id"])
    assert still["id"] == wedding["id"]
    assert [p["name"] for p in still["participants"]] == ["Jane"]
