"""Uniqueness and aliases for people, places and threads; deleting a thread untags."""

from tests.domain import epic, event, family, made, period, person


def test_names_are_unique_without_regard_to_case(session):
    c = family(session)
    person(c, "Mary Murphy")
    r = c.post("/api/people", json={"name": "mary murphy"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "name_taken"


def test_a_deleted_persons_name_can_be_used_again(session):
    c = family(session)
    old = person(c, "Mary")
    c.delete(f"/api/people/{old['id']}")
    assert person(c, "Mary")["id"] != old["id"]


def test_one_alias_can_name_several_people(session):
    c = family(session)
    jim, ann = person(c, "Jim"), person(c, "Ann")
    for who in (jim, ann):
        made(
            c.post(f"/api/people/{who['id']}/aliases", json={"alias": "the kids"}), 200
        )
    found = c.get("/api/people", params={"q": "KIDS"}).json()["items"]
    assert sorted(p["name"] for p in found) == ["Ann", "Jim"]


def test_an_alias_is_kept_once_per_person_and_cannot_be_someone_elses_name(session):
    c = family(session)
    jim = person(c, "Jim")
    person(c, "James")
    c.post(f"/api/people/{jim['id']}/aliases", json={"alias": "Jimmy"})
    again = made(
        c.post(f"/api/people/{jim['id']}/aliases", json={"alias": "jimmy"}), 200
    )
    assert again["aliases"] == ["Jimmy"]
    clash = c.post(f"/api/people/{jim['id']}/aliases", json={"alias": "james"})
    assert clash.status_code == 409
    gone = made(c.delete(f"/api/people/{jim['id']}/aliases/JIMMY"), 200)
    assert gone["aliases"] == []


def test_place_names_are_unique_without_regard_to_case(session):
    c = family(session)
    made(
        c.post(
            "/api/places",
            json={"name": "Erie, PA", "latitude": 42.1, "longitude": -80.1},
        )
    )
    assert c.post("/api/places", json={"name": "erie, pa"}).status_code == 409
    assert (
        c.post("/api/places", json={"name": "Bad", "latitude": 91}).status_code == 422
    )


def test_thread_titles_are_unique_and_slugged(session):
    c = family(session)
    a = made(c.post("/api/threads", json={"title": "The Farm"}))
    assert a["slug"] == "the-farm"
    assert c.post("/api/threads", json={"title": "the farm"}).status_code == 409
    b = made(c.post("/api/threads", json={"title": "The farm!"}))
    assert b["slug"] == "the-farm-2"


def test_deleting_a_thread_untags_and_deletes_nothing_else(session):
    c = family(session)
    farm = made(c.post("/api/threads", json={"title": "The Farm"}))
    navy = period(c, person(c, "Corey")["id"], "Navy")
    ep = epic(c, navy["id"], "Harvests", thread_id=farm["id"])
    ev = event(c, "Haying", thread_id=farm["id"])
    assert c.delete(f"/api/threads/{farm['id']}").status_code == 204
    assert c.get(f"/api/epics/{ep['id']}").json()["thread_id"] is None
    assert c.get(f"/api/events/{ev['id']}").json()["thread_id"] is None


def test_a_person_can_be_linked_to_a_login_once(session):
    from app.accounts.models import User

    c = family(session)
    me = session.query(User).one()
    a = person(c, "Corey", user_id=me.id)
    assert a["user_id"] == me.id
    r = c.post("/api/people", json={"name": "Other", "user_id": me.id})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "login_taken"
