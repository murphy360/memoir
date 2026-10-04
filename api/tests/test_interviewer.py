"""The turn-based interviewer: questions from what was just said, de-duplicated as
they are written, scoped, seeded, ordered, answered by recording, dismissed for good.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.accounts.models import Role, User
from app.ai import registry
from app.ai.costs import AICall
from app.ai.fake import FakeAI
from app.ai.provider import ProviderError
from app.analysis.extract import extract
from app.domain import questions as questions_mod
from app.domain.memories import Memory
from app.domain.questions import Question, QuestionIn
from app.jobs import catalog, queue
from app.jobs.models import Job, JobStatus
from app.jobs.registry import HANDLERS, JobContext, PermanentError
from app.questions import interviewer
from app.questions.generate import generate, tidy
from tests.accounts import member, sign_in
from tests.domain import event, family, made, memory, period, person, place
from tests.test_capture import finalize, recording, upload

TRANSCRIPT = "In the summer of 1968 my brother Jim drove us to Erie in his old car."
QUESTIONS = {
    "questions": [
        {"text": "You said your brother drove. Which brother?", "about": "event"},
        {"text": "What was Jim like then?", "about": "person", "person": "Jim"},
        {"text": "What did that summer mean to you?", "about": "period"},
    ]
}


@pytest.fixture
def ai():
    fake = FakeAI()
    registry.use(fake)
    yield fake
    registry.reset()


def ctx(session, last=True):
    return JobContext(session, 0, attempt=5 if last else 1, max_attempts=5)


def me(session):
    return session.query(User).filter(User.email == "owner@example.org").one()


@pytest.fixture
def told(session):
    """Corey told a story about Jim, placed on an event in his Erie years."""
    c = family(session)
    corey = person(c, "Corey", user_id=me(session).id)
    jim = person(c, "Jim")
    erie = period(c, corey["id"], "Erie years", start_text="1967", end_text="1970")
    trip = event(c, "Driving to Erie", date_text="summer 1968")
    place(c, trip["id"], corey["id"], period_id=erie["id"])
    m = memory(
        c,
        title="Driving to Erie",
        transcript=TRANSCRIPT,
        storyteller_id=corey["id"],
        event_id=trip["id"],
        mentioned_ids=[jim["id"]],
    )
    return {"c": c, "corey": corey, "jim": jim, "erie": erie, "trip": trip, "m": m}


def pending(session):
    return session.scalars(
        select(Question).where(Question.status == "pending").order_by(Question.id)
    ).all()


def test_questions_come_from_the_transcript_scoped_and_for_the_storyteller(
    session, told, ai
):
    ai.data = QUESTIONS
    assert generate(ctx(session), {"memory_id": told["m"]["id"]}) == {
        "state": "done",
        "made": 3,
    }
    rows = pending(session)
    assert [(q.scope, q.event_id, q.person_id, q.period_id) for q in rows] == [
        ("event", told["trip"]["id"], None, None),
        ("person", None, told["jim"]["id"], None),
        ("period", None, None, told["erie"]["id"]),
    ]
    assert {q.asked_of_id for q in rows} == {told["corey"]["id"]}
    assert {q.source_memory_id for q in rows} == {told["m"]["id"]}
    sent = ai.calls[0]["prompt"]
    for part in ("Storyteller: Corey", "Jim", "summer 1968", TRANSCRIPT, "leading"):
        assert part in sent
    assert session.get(Memory, told["m"]["id"]).questions_state == "done"
    cost = session.scalars(select(AICall)).one()
    assert (cost.task, cost.prompt_version) == ("questions", "questions-1")


def test_a_target_that_is_not_known_makes_the_question_general(session, told, ai):
    ai.data = {
        "questions": [
            {"text": "Who is Mary?", "about": "person", "person": "Mary"},
            {"text": "Where did you sleep?", "about": "nonsense"},
        ]
    }
    generate(ctx(session), {"memory_id": told["m"]["id"]})
    assert [q.scope for q in pending(session)] == ["general", "general"]


def test_only_short_single_questions_are_kept():
    assert tidy("Which brother? And what car?") == "Which brother?"
    assert tidy("  Tell me about   the car") == "Tell me about the car?"
    assert tidy("Tell me about the car.") == "Tell me about the car."
    assert tidy(" ".join(["word"] * 30) + "?") is None
    assert tidy("") is None


def test_the_same_text_is_never_pending_twice_whatever_wrote_it(session, told, ai):
    c = told["c"]
    made(c.post("/api/questions", json={"text": "what was jim like THEN"}))
    ai.data = QUESTIONS
    generate(ctx(session), {"memory_id": told["m"]["id"]})
    texts = [q.normalized for q in pending(session)]
    assert texts.count("what was jim like then") == 1
    assert len(texts) == 3


def test_a_race_on_the_same_text_returns_the_winner(session, told, monkeypatch):
    first = questions_mod.add(session, me(session), QuestionIn(text="Who drove?"))
    real = questions_mod._pending
    calls = iter([None])
    monkeypatch.setattr(
        questions_mod,
        "_pending",
        lambda s, a, k: next(calls, None) or real(s, a, k),
    )
    again = questions_mod.add(session, me(session), QuestionIn(text="who drove"))
    assert again.id == first.id
    assert len(pending(session)) == 1


def test_a_dismissed_question_never_returns(session, told, ai):
    c = told["c"]
    ai.data = QUESTIONS
    generate(ctx(session), {"memory_id": told["m"]["id"]})
    gone = pending(session)[0]
    made(c.patch(f"/api/questions/{gone.id}", json={"status": "dismissed"}), 200)
    r = c.patch(f"/api/questions/{gone.id}", json={"status": "answered"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "not_pending"
    back = c.patch(f"/api/questions/{gone.id}", json={"status": "pending"})
    assert back.status_code == 422
    again = memory(c, title="Again", transcript=TRANSCRIPT)
    generate(ctx(session), {"memory_id": again["id"]})
    assert gone.normalized not in [q.normalized for q in pending(session)]
    shown = made(c.get("/api/questions/for-you"), 200)["items"]
    assert gone.id not in [q["id"] for q in shown]


def test_an_empty_archive_shows_the_three_seed_questions_once(session):
    c = family(session)
    shown = made(c.get("/api/questions/for-you"), 200)["items"]
    assert [q["text"] for q in shown] == list(interviewer.SEEDS)
    nxt = made(c.get("/api/questions/next"), 200)
    assert nxt["question"]["text"] == "What should we call you?"
    for q in shown:
        made(c.patch(f"/api/questions/{q['id']}", json={"status": "dismissed"}), 200)
    assert made(c.get("/api/questions/next"), 200) == {
        "question": None,
        "waiting": False,
    }
    assert made(c.get("/api/questions/for-you"), 200)["items"] == []


def ask(c, text, **fields):
    return made(c.post("/api/questions", json={"text": text, **fields}))


def test_next_is_about_the_latest_memory_then_scope_then_age(session, told, ai):
    c, s = told["c"], session
    old = ask(c, "An old general question?")
    ai.data = QUESTIONS
    generate(ctx(s), {"memory_id": told["m"]["id"]})
    shown = [q["text"] for q in made(c.get("/api/questions/for-you"), 200)["items"]]
    assert shown == [
        "You said your brother drove. Which brother?",
        "What did that summer mean to you?",
        "What was Jim like then?",
        old["text"],
    ]
    newer = memory(c, title="Later", transcript="Later on we moved.")
    later = s.get(Memory, newer["id"])
    later.created_at = later.created_at + timedelta(minutes=1)
    s.commit()
    ai.data = {"questions": [{"text": "Why did you move?", "about": "general"}]}
    generate(ctx(s), {"memory_id": newer["id"]})
    nxt = made(c.get("/api/questions/next"), 200)["question"]
    assert nxt["text"] == "Why did you move?"
    assert nxt["about"] == "Later"


def test_a_question_for_someone_else_is_not_yours(session, told, ai):
    ai.data = QUESTIONS
    generate(ctx(session), {"memory_id": told["m"]["id"]})
    member(session, Role.CONTRIBUTOR)
    other = sign_in("contributor@example.org")
    assert made(other.get("/api/questions/for-you"), 200)["items"] == []
    assert len(made(told["c"].get("/api/questions/for-you"), 200)["items"]) == 3


def test_a_private_memory_keeps_its_questions_private(session, told, ai):
    c = told["c"]
    secret = memory(c, title="Secret", transcript="x", visibility="only_me")
    ai.data = {"questions": [{"text": "Who else knew?", "about": "general"}]}
    generate(ctx(session), {"memory_id": secret["id"]})
    # For anyone, so only the memory's visibility keeps it from others.
    for q in pending(session):
        q.asked_of_id = None
    session.commit()
    member(session, Role.CONTRIBUTOR)
    other = sign_in("contributor@example.org")
    assert made(other.get("/api/questions/for-you"), 200)["items"] == []


def test_answering_an_event_question_records_onto_its_event(session, told, tmp_path):
    c = told["c"]
    q = ask(c, "Which car was it?", scope="event", event_id=told["trip"]["id"])
    m = finalize(c, upload(c, recording(tmp_path), question_id=q["id"])["id"])
    assert m["response_to_question_id"] == q["id"]
    assert m["event_id"] == told["trip"]["id"]
    row = session.get(Question, q["id"])
    assert (row.status, row.answered_by_memory_id) == ("answered", m["id"])
    shown = made(
        c.get(
            "/api/questions",
            params={"status": "answered", "answered_by_memory_id": m["id"]},
        ),
        200,
    )["items"]
    assert [x["text"] for x in shown] == ["Which car was it?"]


def test_answering_a_person_question_mentions_them(session, told, tmp_path):
    c = told["c"]
    q = ask(c, "What was Jim like?", scope="person", person_id=told["jim"]["id"])
    m = finalize(c, upload(c, recording(tmp_path), question_id=q["id"])["id"])
    assert m["mentioned_ids"] == [told["jim"]["id"]]


def test_an_answer_about_a_period_is_filed_there_even_undated(
    session, told, tmp_path, ai
):
    c = told["c"]
    q = ask(c, "What was school like?", scope="period", period_id=told["erie"]["id"])
    m = finalize(c, upload(c, recording(tmp_path), question_id=q["id"])["id"])
    placement = made(c.get(f"/api/memories/{m['id']}/placement"), 200)
    assert placement["saved_to"] is None
    assert placement["suggestions"][0]["period_id"] == told["erie"]["id"]
    assert "question" in placement["suggestions"][0]["reason"]
    row = session.get(Memory, m["id"])
    row.transcript = "School was a long walk."
    session.commit()
    ai.data = lambda prompt, schema: (
        {"questions": []}
        if "questions" in schema["properties"]
        else {"title": "The walk to school", "people": [], "places": []}
    )
    extract(ctx(session), {"memory_id": m["id"]})
    saved = made(c.get(f"/api/memories/{m['id']}/placement"), 200)["saved_to"]
    assert saved["period_title"] == "Erie years"
    assert saved["event_title"] == "The walk to school"


def test_waiting_for_the_questions_about_what_was_just_said(session, told, ai):
    c = told["c"]
    m = memory(c, title="Just now", transcript=TRANSCRIPT)
    path = f"/api/questions/next?after_memory_id={m['id']}"
    assert made(c.get(path), 200)["waiting"] is True
    ai.data = QUESTIONS
    generate(ctx(session), {"memory_id": m["id"]})
    nxt = made(c.get(path), 200)
    assert nxt["waiting"] is False
    assert nxt["question"]["source_memory_id"] == m["id"]


def test_with_questions_off_or_no_transcript_nothing_is_waited_for(session, told):
    c = told["c"]
    registry.use(None)
    try:
        assert generate(ctx(session), {"memory_id": told["m"]["id"]}) == {
            "state": "ai_off"
        }
    finally:
        registry.reset()
    path = f"/api/questions/next?after_memory_id={told['m']['id']}"
    assert made(c.get(path), 200)["waiting"] is False
    blank = memory(c, title="Blank")
    assert generate(ctx(session), {"memory_id": blank["id"]})["made"] == 0
    old = session.get(Memory, memory(c, title="Old")["id"])
    old.created_at = old.created_at - timedelta(minutes=10)
    session.commit()
    assert not interviewer.still_coming(old)


def test_a_failure_is_retried_then_given_up(session, told, ai):
    ai.fail_next = 2
    with pytest.raises(ProviderError):
        generate(ctx(session, last=False), {"memory_id": told["m"]["id"]})
    assert session.get(Memory, told["m"]["id"]).questions_state is None
    with pytest.raises(ProviderError):
        generate(ctx(session, last=True), {"memory_id": told["m"]["id"]})
    assert session.get(Memory, told["m"]["id"]).questions_state == "failed"

    def refused(prompt, schema):
        raise ProviderError("no credit", retryable=False)

    ai.structured = lambda prompt, schema, model: refused(prompt, schema)
    with pytest.raises(PermanentError):
        generate(ctx(session, last=False), {"memory_id": told["m"]["id"]})


def test_a_question_reads_with_what_it_is_about(session, told):
    c = told["c"]
    q = ask(c, "Which car?", scope="event", event_id=told["trip"]["id"])
    assert made(c.get(f"/api/questions/{q['id']}"), 200)["about"] == "Driving to Erie"


def test_merging_people_moves_whom_questions_are_for(session, told, ai):
    ai.data = QUESTIONS
    generate(ctx(session), {"memory_id": told["m"]["id"]})
    c = told["c"]
    twin = person(c, "Corey M")
    made(
        c.post(
            f"/api/people/{told['corey']['id']}/merge", json={"into_id": twin["id"]}
        ),
        200,
    )
    assert {q.asked_of_id for q in pending(session)} == {twin["id"]}


def drain(session):
    """Run every queued job, in order, as the worker would."""
    catalog.load()
    while job := queue.claim(session, "test", timedelta(minutes=5)):
        result = HANDLERS[job.kind](JobContext(session, job.id), dict(job.payload))
        queue.succeed(session, job, result)


def test_the_loop_runs_five_questions_deep_on_record_and_stop(session, tmp_path, ai):
    """Each answer is recorded from the question the home shows, and the next
    question is about what was just said."""
    c = family(session)
    person(c, "Corey", user_id=me(session).id)
    rounds = iter(range(1, 10))
    ai.transcript = lambda audio: f"Answer number {next(rounds)}."

    def answer(prompt, schema):
        if "questions" not in schema["properties"]:
            return {"title": "An answer", "people": [], "places": []}
        n = prompt.split("Answer number ")[1].split(".")[0]
        text = f"What came after part {n}?"
        return {"questions": [{"text": text, "about": "general"}]}

    ai.data = answer
    data = recording(tmp_path)
    q = made(c.get("/api/questions/next"), 200)["question"]
    assert q["text"] == "What should we call you?"
    for n in range(1, 6):
        m = finalize(c, upload(c, data, question_id=q["id"])["id"])
        assert made(c.get(f"/api/questions/next?after_memory_id={m['id']}"), 200)[
            "waiting"
        ]
        drain(session)
        nxt = made(c.get(f"/api/questions/next?after_memory_id={m['id']}"), 200)
        assert nxt["waiting"] is False
        assert session.get(Question, q["id"]).answered_by_memory_id == m["id"]
        q = nxt["question"]
        assert q["text"] == f"What came after part {n}?"
        assert q["source_memory_id"] == m["id"]
    assert session.query(Job).filter(Job.status != JobStatus.SUCCEEDED).count() == 0


def test_an_answer_joins_the_story_its_question_came_from(session, told, tmp_path):
    """A follow-up to a placed story, about a person or nothing in particular: the
    answer goes on that story's event, and names the person."""
    c, s = told["c"], session
    jim = {"person_id": told["jim"]["id"]}
    for scope, extra in (("person", jim), ("general", {})):
        q = ask(c, f"A {scope} follow-up?", scope=scope, **extra)
        s.get(Question, q["id"]).source_memory_id = told["m"]["id"]
        s.commit()
        m = finalize(c, upload(c, recording(tmp_path), question_id=q["id"])["id"])
        assert m["event_id"] == told["trip"]["id"], scope
        assert m["mentioned_ids"] == ([told["jim"]["id"]] if extra else [])


def test_a_recording_started_from_an_event_keeps_it_when_answering(
    session, told, tmp_path
):
    c = told["c"]
    other = event(c, "Another day", date_text="1975")
    q = ask(c, "Which car was it?", scope="event", event_id=told["trip"]["id"])
    m = finalize(
        c,
        upload(c, recording(tmp_path), question_id=q["id"], event_id=other["id"])["id"],
    )
    assert m["event_id"] == other["id"]
