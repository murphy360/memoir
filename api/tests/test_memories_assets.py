"""Memories and assets: visibility, the inbox, files and links."""

from app.accounts.models import Role
from tests.accounts import member, sign_in
from tests.domain import event, family, made, memory, person
from tests.test_merge import asset, blob


def test_only_me_memories_are_hidden_from_everyone_else_on_every_list(session):
    c = family(session)
    member(session, Role.CONTRIBUTOR, "ann@example.org")
    ann = sign_in("ann@example.org")
    grandma = person(c, "Grandma")
    ev = event(c, "Christmas")
    secret = memory(
        c,
        title="Secret",
        visibility="only_me",
        event_id=ev["id"],
        storyteller_id=grandma["id"],
    )
    loose = memory(c, title="Loose secret", visibility="only_me")
    shared = memory(c, title="Shared", event_id=ev["id"], storyteller_id=grandma["id"])

    def titles(client, **params):
        return [
            m["title"]
            for m in client.get("/api/memories", params=params).json()["items"]
        ]

    assert sorted(titles(c)) == ["Loose secret", "Secret", "Shared"]
    assert titles(ann) == ["Shared"]
    assert titles(ann, event_id=ev["id"]) == ["Shared"]
    assert titles(ann, person_id=grandma["id"]) == ["Shared"]
    assert titles(ann, inbox=True) == []
    assert titles(c, inbox=True) == ["Loose secret"]
    for hidden in (secret, loose):
        assert ann.get(f"/api/memories/{hidden['id']}").status_code == 404
        assert (
            ann.patch(f"/api/memories/{hidden['id']}", json={"title": "x"}).status_code
            == 404
        )
    assert ann.get(f"/api/memories/{shared['id']}").status_code == 200


def test_the_storytellers_own_login_sees_their_only_me_memories(session):
    from app.accounts.models import User

    c = family(session)
    gran = member(session, Role.VIEWER, "gran@example.org")
    grandma = person(c, "Grandma", user_id=session.get(User, gran.id).id)
    memory(c, title="For me", visibility="only_me", storyteller_id=grandma["id"])
    seen = sign_in("gran@example.org").get("/api/memories").json()["items"]
    assert [m["title"] for m in seen] == ["For me"]


def test_a_memory_whose_event_was_deleted_is_back_in_the_inbox(session):
    c = family(session)
    ev = event(c, "Christmas")
    m = memory(c, title="Tree", event_id=ev["id"])
    assert c.get("/api/memories", params={"inbox": True}).json()["items"] == []
    c.delete(f"/api/events/{ev['id']}")
    inbox = c.get("/api/memories", params={"inbox": True}).json()["items"]
    assert [x["id"] for x in inbox] == [m["id"]]


def test_an_asset_needs_an_uploaded_file_and_finds_duplicates(session):
    c = family(session)
    r = c.post("/api/assets", json={"blob_sha256": "0" * 64, "kind": "photo"})
    assert r.status_code == 422
    sha = blob(session)
    first = asset(c, sha)
    found = c.get("/api/assets", params={"sha256": sha}).json()["items"]
    assert [a["id"] for a in found] == [first["id"]]


def test_unlinked_assets_and_assets_of_deleted_events_are_in_the_inbox(session):
    c = family(session)
    a, b = asset(c, blob(session, b"a")), asset(c, blob(session, b"b"))
    ev = event(c, "Christmas")
    linked = made(
        c.put(
            f"/api/events/{ev['id']}/assets/{a['id']}", json={"relation": "evidence"}
        ),
        200,
    )
    assert linked["event_ids"] == [ev["id"]]
    inbox = [
        x["id"] for x in c.get("/api/assets", params={"inbox": True}).json()["items"]
    ]
    assert inbox == [b["id"]]
    c.delete(f"/api/events/{ev['id']}")
    inbox = [
        x["id"] for x in c.get("/api/assets", params={"inbox": True}).json()["items"]
    ]
    assert sorted(inbox) == sorted([a["id"], b["id"]])


def test_unlinking_an_asset(session):
    c = family(session)
    a = asset(c, blob(session))
    ev = event(c, "Christmas")
    c.put(f"/api/events/{ev['id']}/assets/{a['id']}", json={"relation": "recording"})
    assert (
        made(c.delete(f"/api/events/{ev['id']}/assets/{a['id']}"), 200)["event_ids"]
        == []
    )


def test_questions_are_unique_while_pending(session):
    c = family(session)
    q1 = made(c.post("/api/questions", json={"text": "Where were  you born?"}))
    q2 = made(c.post("/api/questions", json={"text": "where were you BORN?"}))
    assert q1["id"] == q2["id"]
    made(c.patch(f"/api/questions/{q1['id']}", json={"status": "dismissed"}), 200)
    q3 = made(c.post("/api/questions", json={"text": "Where were you born?"}))
    assert q3["id"] != q1["id"]
    assert (
        c.post(
            "/api/questions", json={"text": "About whom?", "scope": "person"}
        ).status_code
        == 422
    )
