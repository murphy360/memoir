"""Helpers for the domain tests: an archive with an owner, and short ways to make
things.
"""

from tests.accounts import owner, sign_in


def family(session):
    """A signed-in owner client for a fresh archive."""
    owner(session)
    return sign_in("owner@example.org")


def made(response, status=201):
    assert response.status_code == status, response.text
    return response.json()


def person(c, name, **fields):
    return made(c.post("/api/people", json={"name": name, **fields}))


def period(c, person_id, title, **fields):
    return made(
        c.post("/api/periods", json={"person_id": person_id, "title": title, **fields})
    )


def epic(c, period_id, title, **fields):
    return made(
        c.post("/api/epics", json={"period_id": period_id, "title": title, **fields})
    )


def event(c, title, **fields):
    return made(c.post("/api/events", json={"title": title, **fields}))


def place(c, event_id, person_id, **placement):
    return made(
        c.put(f"/api/events/{event_id}/participants/{person_id}", json=placement), 200
    )


def memory(c, **fields):
    return made(c.post("/api/memories", json=fields))


def timeline(c, person_id):
    return made(c.get(f"/api/people/{person_id}/events"), 200)["items"]
