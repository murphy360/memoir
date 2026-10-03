"""Recordings: chunked, resumable uploads; finalize into a memory; normalise to MP3."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from app.blobs.models import Blob
from app.capture import audio
from app.capture.jobs import normalize_audio
from app.domain.memories import Memory
from app.jobs.models import Job
from app.jobs.registry import JobContext
from tests.domain import event, family, made, person

CHUNK = 4096


def recording(tmp_path: Path, seconds: float = 3, codec: str = "libopus") -> bytes:
    """A real recording: a tone, encoded as a browser would (Opus in WebM)."""
    out = tmp_path / "take.webm"
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:a",
            codec,
            str(out),
        ],
        check=True,
    )
    return out.read_bytes()


def upload(c, data: bytes, **context) -> dict:
    opened = made(
        c.post(
            "/api/capture/uploads",
            json={"content_type": "audio/webm;codecs=opus", "context": context},
        )
    )
    for offset in range(0, len(data), CHUNK):
        r = c.put(
            f"/api/capture/uploads/{opened['id']}",
            params={"offset": offset},
            content=data[offset : offset + CHUNK],
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 200, r.text
    return opened


def finalize(c, upload_id: str) -> dict:
    return made(c.post(f"/api/capture/uploads/{upload_id}/finalize"), 200)


def run_job(session, memory_id: int) -> dict:
    return normalize_audio(JobContext(session, 0), {"memory_id": memory_id})


def test_a_recording_arrives_in_chunks_and_becomes_a_memory(session, tmp_path):
    c = family(session)
    data = recording(tmp_path)
    opened = upload(c, data, quick=True)
    memory = finalize(c, opened["id"])
    row = session.get(Memory, memory["id"])
    assert row.uploaded_by is not None and row.audio_state == "normalising"
    assert row.capture_context == {"quick": True}
    original = session.get(Blob, row.original_audio_sha256)
    assert original.size_bytes == len(data)
    assert original.content_type == "audio/webm;codecs=opus"
    job = session.query(Job).one()
    assert (job.kind, job.payload) == ("capture.normalize_audio", {"memory_id": row.id})


def test_an_upload_resumes_where_the_server_stopped(session, tmp_path):
    c = family(session)
    data = recording(tmp_path)
    opened = made(c.post("/api/capture/uploads", json={"content_type": "audio/webm"}))
    url = f"/api/capture/uploads/{opened['id']}"

    def send(offset, size=CHUNK):
        return c.put(
            url, params={"offset": offset}, content=data[offset : offset + size]
        )

    assert send(0).status_code == 200
    assert send(CHUNK).status_code == 200
    assert c.get(url).json()["received_bytes"] == 2 * CHUNK
    gap = send(3 * CHUNK)
    assert gap.status_code == 409
    assert gap.json()["error"]["code"] == "wrong_offset"
    assert send(0).json()["received_bytes"] == 2 * CHUNK, "a repeated chunk is ignored"
    for offset in range(2 * CHUNK, len(data), CHUNK):
        assert send(offset).status_code == 200
    memory = finalize(c, opened["id"])
    stored = session.get(Memory, memory["id"]).original_audio_sha256
    assert stored == hashlib.sha256(data).hexdigest()


def test_finalizing_twice_gives_the_same_memory(session, tmp_path):
    c = family(session)
    opened = upload(c, recording(tmp_path))
    first, second = finalize(c, opened["id"]), finalize(c, opened["id"])
    assert first["id"] == second["id"]
    assert session.query(Memory).count() == 1
    assert session.query(Job).count() == 1


def test_an_aborted_upload_takes_nothing_more(session, tmp_path):
    c = family(session)
    opened = made(c.post("/api/capture/uploads", json={"content_type": "audio/webm"}))
    assert c.delete(f"/api/capture/uploads/{opened['id']}").status_code == 204
    r = c.put(
        f"/api/capture/uploads/{opened['id']}", params={"offset": 0}, content=b"x"
    )
    assert r.status_code == 409
    assert c.post(f"/api/capture/uploads/{opened['id']}/finalize").status_code == 409


def test_only_recordings_and_reasonable_chunks(session):
    c = family(session)
    r = c.post("/api/capture/uploads", json={"content_type": "image/jpeg"})
    assert r.status_code == 415
    opened = made(c.post("/api/capture/uploads", json={"content_type": "audio/mp4"}))
    big = c.put(
        f"/api/capture/uploads/{opened['id']}",
        params={"offset": 0},
        content=b"\0" * (8 * 1024 * 1024 + 1),
    )
    assert big.status_code == 413


def test_the_context_travels_with_the_recording(session, tmp_path):
    from app.accounts.models import User

    c = family(session)
    me = session.query(User).one()
    corey = person(c, "Corey", user_id=me.id)
    grandma = person(c, "Grandma")
    ev = event(c, "The wedding")
    q = made(c.post("/api/questions", json={"text": "Who sang?"}))
    opened = upload(
        c,
        recording(tmp_path),
        event_id=ev["id"],
        person_id=grandma["id"],
        question_id=q["id"],
    )
    memory = finalize(c, opened["id"])
    assert memory["event_id"] == ev["id"]
    assert memory["storyteller_id"] == corey["id"]
    assert memory["mentioned_ids"] == [grandma["id"]]
    assert memory["response_to_question_id"] == q["id"]
    people = {
        p["name"]: p["role"]
        for p in c.get(f"/api/events/{ev['id']}").json()["participants"]
    }
    assert people == {"Corey": "storyteller", "Grandma": "mentioned"}


def test_a_context_from_nowhere_is_refused(session):
    c = family(session)
    r = c.post(
        "/api/capture/uploads",
        json={"content_type": "audio/webm", "context": {"event_id": 999}},
    )
    assert r.status_code == 404


def test_normalising_keeps_the_original_and_adds_an_mp3(session, tmp_path):
    c = family(session)
    memory = finalize(c, upload(c, recording(tmp_path, seconds=3))["id"])
    result = run_job(session, memory["id"])
    row = session.get(Memory, memory["id"])
    session.refresh(row)
    assert result["state"] == row.audio_state == "normalised"
    assert row.audio_sha256 != row.original_audio_sha256
    assert session.get(Blob, row.audio_sha256).content_type == "audio/mpeg"
    assert session.get(Blob, row.original_audio_sha256) is not None
    assert row.audio_seconds == pytest.approx(3, abs=0.2)
    shown = c.get(f"/api/memories/{row.id}").json()
    assert (shown["audio_state"], round(shown["audio_seconds"])) == ("normalised", 3)


def test_without_ffmpeg_the_original_is_the_recording(session, tmp_path, monkeypatch):
    c = family(session)
    data = recording(tmp_path)
    memory = finalize(c, upload(c, data)["id"])
    monkeypatch.setattr(audio, "FFMPEG", "ffmpeg-is-not-here")
    result = run_job(session, memory["id"])
    assert result["state"] == "not_normalised"
    assert result["problem"] == "ffmpeg is not installed"
    row = session.get(Memory, memory["id"])
    assert row.audio_sha256 is None
    played = c.get(f"/api/memories/{row.id}/audio")
    assert played.status_code == 200 and played.content == data


def test_a_broken_recording_is_kept_as_it_is(session):
    c = family(session)
    junk = bytes(range(256)) * 50
    memory = finalize(c, upload(c, junk)["id"])
    result = run_job(session, memory["id"])
    assert result["state"] == "not_normalised"
    assert result["problem"].startswith("ffmpeg failed")
    assert c.get(f"/api/memories/{memory['id']}/audio").content == junk


def test_the_recording_plays_and_seeks(session, tmp_path):
    c = family(session)
    data = recording(tmp_path)
    memory = finalize(c, upload(c, data)["id"])
    run_job(session, memory["id"])
    mp3 = c.get(f"/api/memories/{memory['id']}/audio")
    assert mp3.headers["content-type"] == "audio/mpeg"
    part = c.get(f"/api/memories/{memory['id']}/audio", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100
    original = c.get(f"/api/memories/{memory['id']}/audio", params={"original": True})
    assert original.content == data


def test_someone_elses_only_me_recording_does_not_play(session, tmp_path):
    from app.accounts.models import Role
    from tests.accounts import member, sign_in

    c = family(session)
    memory = finalize(c, upload(c, recording(tmp_path))["id"])
    c.patch(f"/api/memories/{memory['id']}", json={"visibility": "only_me"})
    member(session, Role.CONTRIBUTOR, "ann@example.org")
    assert (
        sign_in("ann@example.org")
        .get(f"/api/memories/{memory['id']}/audio")
        .status_code
        == 404
    )


def test_the_worker_knows_every_job_kind():
    from app.jobs import catalog
    from app.jobs.registry import HANDLERS

    catalog.load()
    assert {"capture.normalize_audio", "domain.purge", "system.ping"} <= set(HANDLERS)
