"""Every list pages with a cursor, 50 by default."""

from tests.domain import event, family, person


def test_people_page_fifty_at_a_time_without_repeats(session):
    c = family(session)
    for n in range(120):
        person(c, f"Person {n:03d}")
    seen, cursor, pages = [], None, 0
    while True:
        params = {"cursor": cursor} if cursor else {}
        body = c.get("/api/people", params=params).json()
        seen += [p["name"] for p in body["items"]]
        pages += 1
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert pages == 3
    assert seen == sorted(f"Person {n:03d}" for n in range(120))


def test_the_limit_is_adjustable_and_bounded(session):
    c = family(session)
    for n in range(5):
        person(c, f"P{n}")
    body = c.get("/api/people", params={"limit": 2}).json()
    assert len(body["items"]) == 2 and body["next_cursor"]
    assert c.get("/api/people", params={"limit": 201}).status_code == 422


def test_a_bad_cursor_is_refused(session):
    c = family(session)
    r = c.get("/api/people", params={"cursor": "not-a-cursor"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_cursor"


def test_events_page_by_date_with_undated_last(session, engine):
    from sqlalchemy import text

    c = family(session)
    ids = {t: event(c, t)["id"] for t in ("undated", "1990", "1960", "1975")}
    with engine.begin() as conn:
        for title in ("1990", "1960", "1975"):
            conn.execute(
                text(
                    "UPDATE events SET date_start = make_date(:y, 1, 1) WHERE id = :i"
                ),
                {"y": int(title), "i": ids[title]},
            )
    first = c.get("/api/events", params={"limit": 2}).json()
    rest = c.get("/api/events", params={"cursor": first["next_cursor"]}).json()
    order = [e["title"] for e in first["items"] + rest["items"]]
    assert order == ["1960", "1975", "1990", "undated"]
