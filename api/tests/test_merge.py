"""Merging two events, two people, two periods (requirements 3.2)."""

from app.accounts.models import Role, User
from tests.accounts import member
from tests.domain import (
    epic,
    event,
    family,
    made,
    memory,
    period,
    person,
    place,
    timeline,
)


def blob(session, data=b"photo"):
    from app.blobs.store import BlobStore
    from app.core.settings import get_settings

    return (
        BlobStore(get_settings().blob_root)
        .put_bytes(session, data, "image/jpeg")
        .sha256
    )


def asset(c, sha):
    return made(c.post("/api/assets", json={"blob_sha256": sha, "kind": "photo"}))


def test_merging_events_moves_everything_and_fills_gaps(session):
    c = family(session)
    corey, jane = person(c, "Corey"), person(c, "Jane")
    navy = period(c, corey["id"], "Navy")
    src = event(c, "Wedding", description="In the rain", date_text="June 2008")
    dst = event(c, "Our wedding")
    place(c, src["id"], corey["id"], period_id=navy["id"])
    place(c, dst["id"], corey["id"])
    place(c, src["id"], jane["id"])
    m = memory(c, title="The rain", event_id=src["id"])
    shared, own = asset(c, blob(session, b"a")), asset(c, blob(session, b"b"))
    for a in (shared, own):
        c.put(f"/api/events/{src['id']}/assets/{a['id']}", json={})
    c.put(f"/api/events/{dst['id']}/assets/{shared['id']}", json={})
    q = made(
        c.post(
            "/api/questions",
            json={"text": "Who sang?", "scope": "event", "event_id": src["id"]},
        )
    )

    merged = made(
        c.post(f"/api/events/{src['id']}/merge", json={"into_id": dst["id"]}), 200
    )
    assert merged["title"] == "Our wedding"
    assert (merged["description"], merged["date_text"]) == ("In the rain", "June 2008")
    by_name = {p["name"]: p for p in merged["participants"]}
    assert set(by_name) == {"Corey", "Jane"}
    assert (
        by_name["Corey"]["period_id"] == navy["id"]
    ), "the target took the source's placement"
    assert c.get(f"/api/memories/{m['id']}").json()["event_id"] == dst["id"]
    linked = c.get("/api/assets", params={"event_id": dst["id"]}).json()["items"]
    assert sorted(a["id"] for a in linked) == sorted([shared["id"], own["id"]])
    [moved] = c.get("/api/questions").json()["items"]
    assert (moved["id"], moved["event_id"]) == (q["id"], dst["id"])
    assert c.get(f"/api/events/{src['id']}").status_code == 404


def test_merging_people_moves_everything_and_keeps_the_old_name(session):
    c = family(session)
    mom, mother = person(c, "Mom"), person(c, "Mary Murphy", phone="555")
    c.post(f"/api/people/{mom['id']}/aliases", json={"alias": "Mama"})
    hers = period(c, mom["id"], "Childhood")
    period(c, mother["id"], "Childhood")
    ev, both = event(c, "Christmas 1974"), event(c, "Easter")
    place(c, ev["id"], mom["id"], period_id=hers["id"])
    place(c, both["id"], mom["id"], period_id=hers["id"])
    place(c, both["id"], mother["id"])
    told = memory(c, storyteller_id=mom["id"], mentioned_ids=[mom["id"], mother["id"]])

    merged = made(
        c.post(f"/api/people/{mom['id']}/merge", json={"into_id": mother["id"]}), 200
    )
    assert sorted(merged["aliases"]) == ["Mama", "Mom"]
    assert merged["phone"] == "555"
    periods = c.get("/api/periods", params={"person_id": mother["id"]}).json()["items"]
    assert sorted(p["slug"] for p in periods) == ["childhood", "childhood-2"]
    entries = {e["title"]: e for e in timeline(c, mother["id"])}
    assert set(entries) == {"Christmas 1974", "Easter"}
    assert entries["Easter"]["period_id"] == hers["id"]
    assert len(entries["Easter"]["participants"]) == 1
    m = c.get(f"/api/memories/{told['id']}").json()
    assert (m["storyteller_id"], m["mentioned_ids"]) == (mother["id"], [mother["id"]])
    assert c.get(f"/api/people/{mom['id']}").status_code == 404
    assert (
        c.get("/api/people", params={"q": "mama"}).json()["items"][0]["id"]
        == mother["id"]
    )


def test_a_login_moves_to_the_merged_person_but_two_logins_do_not_merge(session):
    c = family(session)
    me = session.query(User).one()
    other = member(session, Role.VIEWER)
    a = person(c, "Corey", user_id=me.id)
    b = person(c, "C. Murphy")
    merged = made(
        c.post(f"/api/people/{a['id']}/merge", json={"into_id": b["id"]}), 200
    )
    assert merged["user_id"] == me.id
    d = person(c, "Viewer", user_id=other.id)
    r = c.post(f"/api/people/{d['id']}/merge", json={"into_id": b["id"]})
    assert r.status_code == 409


def test_merging_periods_moves_their_epics_and_events(session):
    c = family(session)
    corey = person(c, "Corey")
    a, b = (
        period(c, corey["id"], "Navy", start_text="1990"),
        period(c, corey["id"], "Service"),
    )
    ep = epic(c, a["id"], "Norfolk")
    ev = event(c, "Shore leave")
    place(c, ev["id"], corey["id"], epic_id=ep["id"])
    merged = made(
        c.post(f"/api/periods/{a['id']}/merge", json={"into_id": b["id"]}), 200
    )
    assert merged["start_text"] == "1990"
    assert c.get(f"/api/epics/{ep['id']}").json()["period_id"] == b["id"]
    [entry] = timeline(c, corey["id"])
    assert (entry["period_id"], entry["epic_id"]) == (b["id"], ep["id"])


def test_periods_merge_only_within_one_life(session):
    c = family(session)
    a = period(c, person(c, "Corey")["id"], "Navy")
    b = period(c, person(c, "Jane")["id"], "Hers")
    assert (
        c.post(f"/api/periods/{a['id']}/merge", json={"into_id": b["id"]}).status_code
        == 422
    )
    assert (
        c.post(f"/api/periods/{a['id']}/merge", json={"into_id": a["id"]}).status_code
        == 422
    )
