"""Transcription and extraction, driven by a fake provider (requirements 6.1 to 6.3)."""

import json
import subprocess
from datetime import date

import httpx
import pytest

from app.ai import registry
from app.ai.costs import AICall
from app.ai.fake import FakeAI
from app.ai.gemini import Gemini
from app.ai.provider import Audio, ProviderError
from app.analysis.extract import extract
from app.analysis.transcribe import transcribe
from app.domain.memories import Memory
from app.domain.people import Person
from app.domain.places import Place
from app.jobs.models import Job
from app.jobs.registry import JobContext
from tests.domain import family, made, memory, person
from tests.test_capture import finalize, recording, run_job, upload

FIXTURE = "My name is Corey, in the summer of 1968 my brother Jim and I drove to Erie."
AS_THE_MODEL_READS_IT = {
    "title": "Driving to Erie with my brother Jim",
    "description": "Corey and his brother Jim drove to Erie in the summer of 1968.",
    "date_text": "summer of 1968",
    "date_precision": "approximate",
    "storyteller_name": "Corey",
    "people": ["Jim", "Corey"],
    "places": ["Erie"],
    "tone": "reflective",
    "relationship_effects": [],
}


@pytest.fixture
def ai():
    fake = FakeAI()
    registry.use(fake)
    yield fake
    registry.reset()


def ctx(session, last=True):
    return JobContext(session, 0, attempt=5 if last else 1, max_attempts=5)


def recorded_memory(c, session, tmp_path, seconds=3):
    m = finalize(c, upload(c, recording(tmp_path, seconds))["id"])
    run_job(session, m["id"])
    return m


def test_a_recording_is_transcribed_and_its_cost_recorded(session, tmp_path, ai):
    c = family(session)
    ai.transcript = FIXTURE
    m = recorded_memory(c, session, tmp_path)
    result = transcribe(ctx(session), {"memory_id": m["id"]})
    row = session.get(Memory, m["id"])
    session.refresh(row)
    assert result["state"] == "done"
    assert (row.transcript, row.transcript_state, row.transcript_source) == (
        FIXTURE,
        "done",
        "machine",
    )
    cost = session.query(AICall).one()
    assert (cost.task, cost.provider, cost.prompt_version, cost.ok) == (
        "transcribe",
        "fake",
        "transcribe-1",
        True,
    )
    assert cost.input_tokens > 0 and cost.memory_id == row.id
    assert ai.calls[0]["mime"] == "audio/mpeg", "the normalised MP3 is what is sent"
    assert session.query(Job).filter(Job.kind == "analysis.extract").count() == 1


def test_normalising_queues_transcription(session, tmp_path):
    c = family(session)
    m = recorded_memory(c, session, tmp_path)
    queued = session.query(Job).filter(Job.kind == "analysis.transcribe").one()
    assert queued.payload == {"memory_id": m["id"]}


def test_with_no_key_ai_is_off_the_recording_is_safe_and_a_retry_fills_it_in(
    session, tmp_path
):
    c = family(session)
    registry.use(None)
    try:
        m = recorded_memory(c, session, tmp_path)
        assert transcribe(ctx(session), {"memory_id": m["id"]}) == {"state": "ai_off"}
        shown = c.get(f"/api/memories/{m['id']}").json()
        assert (shown["transcript_state"], shown["audio_state"]) == (
            "ai_off",
            "normalised",
        )
        assert c.get("/api/ai/status").json()["enabled"] is False
        fake = FakeAI()
        fake.transcript = "Now it works."
        registry.use(fake)
        again = made(c.post(f"/api/memories/{m['id']}/transcribe"), 200)
        assert again["transcript_state"] == "transcribing"
        transcribe(ctx(session), {"memory_id": m["id"]})
        assert c.get(f"/api/memories/{m['id']}").json()["transcript"] == "Now it works."
    finally:
        registry.reset()


def test_the_owner_can_turn_transcription_off(session, tmp_path, ai):
    c = family(session)
    c.patch("/api/settings", json={"ai_transcription": False})
    m = recorded_memory(c, session, tmp_path)
    assert transcribe(ctx(session), {"memory_id": m["id"]})["state"] == "ai_off"
    assert ai.calls == []


def test_a_failure_is_retried_then_shown_and_the_audio_kept(session, tmp_path, ai):
    c = family(session)
    m = recorded_memory(c, session, tmp_path)
    ai.fail_next = 2
    with pytest.raises(ProviderError):
        transcribe(ctx(session, last=False), {"memory_id": m["id"]})
    assert session.get(Memory, m["id"]).transcript_state == "transcribing"
    with pytest.raises(ProviderError):
        transcribe(ctx(session, last=True), {"memory_id": m["id"]})
    row = session.get(Memory, m["id"])
    session.refresh(row)
    assert row.transcript_state == "failed"
    assert "fail" in row.analysis_error
    assert row.audio_sha256 is not None
    assert [r.ok for r in session.query(AICall).order_by(AICall.id)] == [False, False]


def test_audio_over_the_inline_limit_is_cut_and_still_transcribed(
    session, tmp_path, ai
):
    c = family(session)
    m = finalize(c, upload(c, recording(tmp_path, seconds=75))["id"])
    run_job(session, m["id"])
    ai.inline_limit = 300 * 1024
    ai.transcript = lambda audio: f"[{len(audio.data) // 1024} KB]"
    result = transcribe(ctx(session), {"memory_id": m["id"]})
    assert result["parts"] >= 3
    assert all(call["bytes"] <= ai.inline_limit for call in ai.calls)
    assert session.query(AICall).count() == result["parts"]
    assert session.get(Memory, m["id"]).transcript.count("KB]") == result["parts"]


def test_a_transcript_a_person_edited_is_never_replaced(session, tmp_path, ai):
    c = family(session)
    m = recorded_memory(c, session, tmp_path)
    c.patch(f"/api/memories/{m['id']}", json={"transcript": "What she really said."})
    assert transcribe(ctx(session), {"memory_id": m["id"]})["state"] == "kept"
    assert session.get(Memory, m["id"]).transcript == "What she really said."


def test_extraction_reads_the_fixture_transcript(session, ai):
    c = family(session)
    ai.data = AS_THE_MODEL_READS_IT
    m = memory(c, transcript=FIXTURE)
    assert extract(ctx(session), {"memory_id": m["id"]})["state"] == "done"
    shown = c.get(f"/api/memories/{m['id']}").json()
    corey = session.get(Person, shown["storyteller_id"])
    jim = session.get(Person, shown["mentioned_ids"][0])
    erie = session.get(Place, shown["place_ids"][0])
    assert (corey.name, jim.name, erie.name) == ("Corey", "Jim", "Erie")
    assert shown["mentioned_ids"] == [jim.id], "the storyteller is not mentioned"
    assert corey.needs_review and jim.needs_review and erie.needs_review
    assert (shown["date_start"], shown["date_end"]) == ("1968-06-01", "1968-08-31")
    assert shown["title"] == "Driving to Erie with my brother Jim"
    assert "narration" not in shown["title"].lower()
    assert shown["tone"] == "reflective"
    assert shown["extraction_state"] == "done"
    assert "Corey" in ai.calls[0]["prompt"] or "Transcript" in ai.calls[0]["prompt"]
    cost = session.query(AICall).one()
    assert (cost.task, cost.prompt_version) == ("extract", "extract-1")


def test_names_resolve_through_aliases_and_an_alias_can_name_several(session, ai):
    c = family(session)
    ann, jim = person(c, "Ann"), person(c, "Jim")
    for p in (ann, jim):
        c.post(f"/api/people/{p['id']}/aliases", json={"alias": "the kids"})
    grandma = person(c, "Grandma Murphy")
    c.post(f"/api/people/{grandma['id']}/aliases", json={"alias": "Gran"})
    ai.data = {
        **AS_THE_MODEL_READS_IT,
        "storyteller_name": "Gran",
        "people": ["the kids"],
    }
    m = memory(c, transcript="Gran here. The kids were small.")
    extract(ctx(session), {"memory_id": m["id"]})
    shown = c.get(f"/api/memories/{m['id']}").json()
    assert shown["storyteller_id"] == grandma["id"]
    assert sorted(shown["mentioned_ids"]) == sorted([ann["id"], jim["id"]])
    assert session.query(Person).filter(Person.needs_review.is_(True)).count() == 0


def test_an_ambiguous_storyteller_is_left_for_a_person(session, ai):
    c = family(session)
    for name in ("Mary", "Margaret"):
        p = person(c, name)
        c.post(f"/api/people/{p['id']}/aliases", json={"alias": "Mom"})
    ai.data = {**AS_THE_MODEL_READS_IT, "storyteller_name": "Mom", "people": []}
    m = memory(c, transcript="Mom speaking.")
    extract(ctx(session), {"memory_id": m["id"]})
    row = session.get(Memory, m["id"])
    assert row.storyteller_id is None
    assert row.extracted["ambiguous_storyteller"] == "Mom"


def test_what_a_person_typed_wins_over_extraction(session, ai):
    c = family(session)
    ai.data = AS_THE_MODEL_READS_IT
    m = memory(c, transcript=FIXTURE, title="The Erie trip", date_text="July 1968")
    extract(ctx(session), {"memory_id": m["id"]})
    shown = c.get(f"/api/memories/{m['id']}").json()
    assert (shown["title"], shown["date_text"]) == ("The Erie trip", "July 1968")


def test_extraction_without_a_transcript_or_after_failures_needs_details(session, ai):
    c = family(session)
    empty = memory(c, title="Nothing said")
    assert extract(ctx(session), {"memory_id": empty["id"]})["state"] == "needs_details"
    m = memory(c, transcript=FIXTURE)
    ai.fail_next = 1
    with pytest.raises(ProviderError):
        extract(ctx(session, last=True), {"memory_id": m["id"]})
    assert session.get(Memory, m["id"]).extraction_state == "needs_details"
    assert session.query(AICall).filter(AICall.ok.is_(False)).count() == 1


def test_the_owner_sees_what_ai_cost(session, tmp_path, ai):
    c = family(session)
    m = recorded_memory(c, session, tmp_path)
    transcribe(ctx(session), {"memory_id": m["id"]})
    ai.data = AS_THE_MODEL_READS_IT
    extract(ctx(session), {"memory_id": m["id"]})
    usage = made(c.get("/api/ai/usage"), 200)
    assert {u["task"]: u["calls"] for u in usage} == {"extract": 1, "transcribe": 1}
    status = made(c.get("/api/ai/status"), 200)
    assert status == {
        "enabled": True,
        "provider": "fake",
        "model": "gemini-2.5-flash",
        "transcription": True,
        "extraction": True,
    }


def test_gemini_sends_its_key_in_a_header_and_reads_usage():
    seen = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["key"] = (
            str(request.url),
            request.headers.get("x-goog-api-key"),
        )
        seen["body"] = json.loads(request.content)
        text = (
            json.dumps({"title": "x"})
            if "responseSchema" in request.content.decode()
            else "hello"
        )
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": text}]}}],
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 3},
            },
        )

    g = Gemini(
        "secret-key", 10, client=httpx.Client(transport=httpx.MockTransport(answer))
    )
    heard = g.transcribe(Audio(b"abc", "audio/mpeg"), "Transcribe", "gemini-2.5-flash")
    assert (heard.text, heard.input_tokens, heard.output_tokens) == ("hello", 12, 3)
    assert seen["key"] == "secret-key" and "secret-key" not in seen["url"]
    assert (
        seen["body"]["contents"][0]["parts"][1]["inline_data"]["mime_type"]
        == "audio/mpeg"
    )
    read = g.structured("Extract", {"type": "object"}, "gemini-2.5-flash")
    assert read.data == {"title": "x"}


BROKE = {"error": {"code": 402, "message": "Your prepayment credits are depleted."}}


@pytest.mark.parametrize(
    "status,body,message,retryable",
    [
        (429, {}, "Gemini answered 429: Too Many Requests", True),
        (503, {}, "Gemini answered 503: Service Unavailable", True),
        (
            402,
            BROKE,
            "Gemini answered 402: Your prepayment credits are depleted.",
            False,
        ),
        (403, {}, "Gemini answered 403: Forbidden", False),
        (
            200,
            {"promptFeedback": {"blockReason": "SAFETY"}},
            "Gemini gave no answer (SAFETY)",
            True,
        ),
    ],
)
def test_gemini_failures_say_why_and_whether_to_retry(status, body, message, retryable):
    transport = httpx.MockTransport(lambda r: httpx.Response(status, json=body))
    g = Gemini("k", 10, client=httpx.Client(transport=transport))
    with pytest.raises(ProviderError) as caught:
        g.text("hi", "m")
    assert (str(caught.value), caught.value.retryable) == (message, retryable)


def test_a_refusal_that_waiting_will_not_fix_fails_at_once_with_the_reason(
    session, tmp_path, ai
):
    from app.jobs.registry import PermanentError

    c = family(session)
    m = recorded_memory(c, session, tmp_path)

    def refused(audio):
        raise ProviderError(
            "Gemini answered 402: credits are depleted", retryable=False
        )

    ai.transcript = refused
    with pytest.raises(PermanentError):
        transcribe(ctx(session, last=False), {"memory_id": m["id"]})
    shown = c.get(f"/api/memories/{m['id']}").json()
    assert shown["transcript_state"] == "failed"
    assert shown["analysis_error"] == "Gemini answered 402: credits are depleted"


def test_no_key_means_no_provider(settings):
    registry.reset()
    assert (
        registry.provider(settings.model_copy(update={"gemini_api_key": None})) is None
    )
    assert registry.model_for(settings, "transcribe") == "gemini-2.5-flash"


def test_fixture_dates_read_as_expected():
    from app.dates.grammar import parse

    assert parse("summer of 1968").start == date(1968, 6, 1)
    assert subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode == 0
