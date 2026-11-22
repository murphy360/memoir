"""The MCP tools, as the owner, a contributor and a viewer: what each may see and do,
visibility, telling a story, and what ends an agent's access."""

import logging

import pytest

from app.accounts.models import Role
from app.ai import registry
from app.domain.memories import Memory
from app.domain.questions import Question
from tests.accounts import member, sign_in
from tests.agents import agent_client, call, connect, rpc, tool_names
from tests.domain import event, family, made, memory, period, person, place

READS = {
    "whoami",
    "search_memories",
    "get_memory",
    "timeline",
    "list_people",
    "next_question",
}


@pytest.fixture
def ai_off():
    registry.use(None)
    yield
    registry.reset()


@pytest.fixture
def home(session, ai_off):
    """An owner with a period and an event in 1968; a contributor and a viewer."""
    owner = family(session)
    me = made(owner.get("/api/me/person"), 200)
    sixties = period(owner, me["id"], "Growing up", start_text="1960", end_text="1969")
    fair = event(owner, "The county fair", date_text="August 1968")
    place(owner, fair["id"], me["id"], period_id=sixties["id"])
    member(session, Role.CONTRIBUTOR)
    member(session, Role.VIEWER)
    return {"owner": owner, "me": me, "sixties": sixties, "fair": fair}


def test_a_viewer_sees_the_read_tools_and_is_refused_tell_story(home):
    viewer = connect("viewer@example.org")["access_token"]
    c = agent_client()
    assert tool_names(c, viewer) == READS
    failed, text = call(c, viewer, "tell_story", story="We drove to the lake.")
    assert failed and "role does not allow" in text
    contributor = connect("contributor@example.org")["access_token"]
    assert tool_names(c, contributor) == READS | {"tell_story"}


@pytest.mark.parametrize(
    "email", ["owner@example.org", "contributor@example.org", "viewer@example.org"]
)
def test_every_read_tool_answers_each_role(home, email):
    access = connect(email)["access_token"]
    c = agent_client()
    failed, me = call(c, access, "whoami")
    assert not failed and me["email"] == email and me["agent"] == "Claude"
    assert me["can_tell_stories"] == (email != "viewer@example.org")
    m = memory(home["owner"], title="The fair", transcript="Corn dogs at the fair.")
    assert (
        call(c, access, "search_memories", query="corn")[1]["items"][0]["id"] == m["id"]
    )
    assert call(c, access, "get_memory", memory_id=m["id"])[1]["transcript"]
    life = call(c, access, "timeline", person_id=home["me"]["id"])[1]
    assert life["periods"][0]["events"][0]["title"] == "The county fair"
    assert call(c, access, "list_people")[1]["items"]
    assert "question" in call(c, access, "next_question")[1]


def test_search_never_returns_a_memory_hidden_from_the_caller(home, session):
    owner = home["owner"]
    memory(
        owner,
        title="Private",
        transcript="A secret about the barn.",
        visibility="only_me",
    )
    shared = memory(
        owner, title="Shared", transcript="The barn burned in 1971.", date_text="1971"
    )
    access = connect("viewer@example.org")["access_token"]
    c = agent_client()
    found = call(c, access, "search_memories", query="barn")[1]["items"]
    assert [m["id"] for m in found] == [shared["id"]]
    hidden = session.query(Memory).filter_by(title="Private").one()
    failed, text = call(c, access, "get_memory", memory_id=hidden.id)
    assert failed and "No such memory" in text
    owner_access = connect("owner@example.org")["access_token"]
    assert len(call(c, owner_access, "search_memories", query="barn")[1]["items"]) == 2


def test_search_filters_by_date_and_person(home):
    owner = home["owner"]
    aunt = person(owner, "Aunt Rose")
    early = memory(owner, title="Early", transcript="x", date_text="1955")
    late = memory(
        owner,
        title="Late",
        transcript="x",
        date_text="1980",
        mentioned_ids=[aunt["id"]],
    )
    access = connect("owner@example.org")["access_token"]
    c = agent_client()

    def ids(**filters):
        return [
            m["id"] for m in call(c, access, "search_memories", **filters)[1]["items"]
        ]

    assert ids(date_from="1970") == [late["id"]]
    assert ids(date_to="1960s") == [early["id"]]
    assert ids(person_id=aunt["id"]) == [late["id"]]
    failed, text = call(c, access, "search_memories", date_from="someday")
    assert failed and "Could not read this date" in text


def test_tell_story_files_it_and_says_who_told_it(home, session):
    access = connect("contributor@example.org", "Claude")["access_token"]
    owner_access = connect("owner@example.org", "Claude")["access_token"]
    failed, told = call(
        agent_client(),
        owner_access,
        "tell_story",
        story="We had corn dogs at the county fair.",
        title="Corn dogs",
        date="August 1968",
    )
    assert not failed, told
    assert told["status"] == "filed"
    assert told["filed"]["event"] == "The county fair"
    assert told["filed"]["period"] == "Growing up"
    assert told["link"].endswith(f"/memoir/memories/{told['memory_id']}")
    shown = made(home["owner"].get(f"/api/memories/{told['memory_id']}"), 200)
    assert shown["told_through"] == "Claude"
    assert shown["transcript"] == "We had corn dogs at the county fair."
    row = session.get(Memory, told["memory_id"])
    assert row.capture_context == {"quick": True}
    assert row.transcript_source == "agent"
    failed, told = call(agent_client(), access, "tell_story", story="No date here.")
    assert not failed and told["status"].startswith("waiting to be placed")


def test_tell_story_answers_a_question(home, session):
    access = connect("owner@example.org")["access_token"]
    c = agent_client()
    asked = call(c, access, "next_question")[1]["question"]
    failed, told = call(
        c, access, "tell_story", story="In Ohio, in 1950.", question_id=asked["id"]
    )
    assert not failed, told
    question = session.get(Question, asked["id"])
    session.refresh(question)
    assert question.status == "answered"
    assert question.answered_by_memory_id == told["memory_id"]


def test_tell_story_needs_words(home):
    access = connect("owner@example.org")["access_token"]
    failed, text = call(agent_client(), access, "tell_story", story="   ")
    assert failed and "in words" in text


def test_with_ai_on_extraction_files_an_undated_story(home, session):
    from app.ai.fake import FakeAI
    from app.jobs.models import Job

    registry.use(FakeAI())
    access = connect("owner@example.org")["access_token"]
    failed, told = call(
        agent_client(), access, "tell_story", story="Corn dogs at the fair."
    )
    assert not failed
    assert told["status"].startswith("saved: Memoir files it")
    job = session.query(Job).filter_by(kind="analysis.extract").one()
    assert job.payload == {"memory_id": told["memory_id"]}


def test_disconnecting_on_the_profile_page_ends_the_agent(home):
    agent = connect("contributor@example.org", "ChatGPT")
    browser = sign_in("contributor@example.org")
    listed = made(browser.get("/api/me/agents"), 200)
    assert [a["name"] for a in listed] == ["ChatGPT"]
    assert listed[0]["last_used_at"]
    assert browser.delete(f"/api/me/agents/{listed[0]['id']}").status_code == 204
    assert rpc(agent_client(), agent["access_token"], "tools/list").status_code == 401
    assert made(browser.get("/api/me/agents"), 200) == []
    owner_list = made(home["owner"].get("/api/me/agents"), 200)
    assert owner_list == []
    assert home["owner"].delete(f"/api/me/agents/{listed[0]['id']}").status_code == 404


def test_a_removed_user_or_a_reset_password_ends_their_agents(home, session):
    from app.accounts.models import User

    viewer = connect("viewer@example.org")["access_token"]
    contributor = connect("contributor@example.org")
    ids = {u.email: u.id for u in session.query(User).all()}
    owner = home["owner"]
    assert owner.delete(f"/api/users/{ids['viewer@example.org']}").status_code == 204
    assert rpc(agent_client(), viewer, "tools/list").status_code == 401
    r = owner.post(
        f"/api/users/{ids['contributor@example.org']}/temporary-password",
        json={"password": "a brand new password"},
    )
    assert r.status_code == 204, r.text
    assert (
        rpc(agent_client(), contributor["access_token"], "tools/list").status_code
        == 401
    )
    refreshed = agent_client().post(
        "/api/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": contributor["refresh_token"],
            "client_id": contributor["client_id"],
        },
    )
    assert refreshed.json()["error"] == "invalid_grant"


def test_logs_carry_the_client_and_tool_never_the_story(home, caplog):
    agent = connect("owner@example.org")
    with caplog.at_level(logging.INFO):
        call(
            agent_client(),
            agent["access_token"],
            "tell_story",
            story="The secret recipe.",
        )
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert f"tool=tell_story client={agent['client_id']}" in logged
    assert "secret recipe" not in logged
