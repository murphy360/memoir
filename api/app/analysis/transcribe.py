"""Transcription: the recording's words, written on the memory (requirements 6.2).

Audio larger than the provider takes in one request is cut into segments with ffmpeg and
transcribed piece by piece. A transcript a person edited is never replaced by a job.
"""

import subprocess
import tempfile
from pathlib import Path

from app.ai import registry
from app.ai.costs import recorded
from app.ai.provider import Audio, ProviderError
from app.analysis.common import ai_for, load
from app.blobs.models import Blob
from app.blobs.store import BlobStore
from app.capture import audio as ffmpeg
from app.core.settings import Settings
from app.jobs import queue
from app.jobs.registry import JobContext, PermanentError, handler

PROMPT_VERSION = "transcribe-1"
PROMPT = (
    "Transcribe this recording of someone telling a family memory. Write exactly what "
    "is said, word for word, in the language spoken. Return plain text only: no title, "
    "no summary, no timestamps. If more than one person speaks, start each change of "
    "speaker on a new line with 'Speaker 1:', 'Speaker 2:' and so on. Write [unclear] "
    "for words you cannot make out."
)


def _cut(path: Path, length: int, workdir: Path) -> list[Path]:
    for old in workdir.glob("part*.mp3"):
        old.unlink()
    subprocess.run(
        [
            ffmpeg.FFMPEG,
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-b:a",
            "128k",
            "-f",
            "segment",
            "-segment_time",
            str(length),
            str(workdir / "part%03d.mp3"),
        ],
        check=True,
        timeout=60 * 60,
    )
    return sorted(workdir.glob("part*.mp3"))


def segments(path: Path, mime: str, limit: int, workdir: Path) -> list[Audio]:
    """The recording as pieces that each fit in one request (MP3, cut on time). Pieces
    are sized from the limit and cut shorter again if one still comes out too big."""
    if path.stat().st_size <= limit:
        return [Audio(path.read_bytes(), mime)]
    seconds = ffmpeg.duration(path) or 0
    if not seconds:
        raise ProviderError("the recording is too long to send and cannot be cut")
    # 128 kbps MP3 is 16 KB a second; leave room for the container.
    length = max(1, int(limit * 0.8 / 16_000))
    for _ in range(6):
        parts = _cut(path, length, workdir)
        if all(p.stat().st_size <= limit for p in parts):
            return [Audio(p.read_bytes(), "audio/mpeg") for p in parts]
        length = max(1, length // 2)
    raise ProviderError("the recording could not be cut small enough to send")


def _source(ctx: JobContext, memory, settings: Settings) -> tuple[Path, str]:
    sha = memory.audio_sha256 or memory.original_audio_sha256
    if sha is None:
        raise ProviderError("the memory has no recording")
    store = BlobStore(settings.blob_root)
    store.verify(sha)
    return store.path(sha), ctx.session.get(Blob, sha).content_type.split(";")[0]


@handler("analysis.transcribe")
def transcribe(ctx: JobContext, payload: dict) -> dict:
    memory = load(ctx.session, payload["memory_id"])
    if memory.transcript_source == "manual":
        return {"state": "kept", "reason": "a person edited the transcript"}
    provider, settings = ai_for(ctx.session, memory, "ai_transcription", "transcribe")
    if provider is None:
        memory.transcript_state = "ai_off"
        ctx.session.commit()
        return {"state": "ai_off"}
    memory.transcript_state = "transcribing"
    ctx.session.commit()
    model = registry.model_for(settings, "transcribe", provider.name)
    try:
        path, mime = _source(ctx, memory, settings)
        with tempfile.TemporaryDirectory() as tmp:
            pieces = segments(path, mime, provider.inline_limit, Path(tmp))
            texts = []
            for n, piece in enumerate(pieces, 1):
                ctx.progress(step="transcribing", part=n, parts=len(pieces))
                answer = recorded(
                    ctx.session,
                    provider,
                    lambda piece=piece: provider.transcribe(piece, PROMPT, model),
                    task="transcribe",
                    model=model,
                    prompt_version=PROMPT_VERSION,
                    archive_id=memory.archive_id,
                    memory_id=memory.id,
                )
                texts.append(answer.text.strip())
    except (ProviderError, subprocess.SubprocessError) as exc:
        retryable = getattr(exc, "retryable", True)
        if ctx.last_attempt or not retryable:
            memory.transcript_state = "failed"
            memory.analysis_error = str(exc)[:500]
            ctx.session.commit()
        if not retryable:
            raise PermanentError(str(exc)) from exc
        raise
    memory.transcript = "\n\n".join(t for t in texts if t)
    memory.transcript_state, memory.transcript_source = "done", "machine"
    memory.analysis_error = None
    ctx.session.commit()
    queue.enqueue(ctx.session, "analysis.extract", {"memory_id": memory.id})
    return {"state": "done", "parts": len(texts), "characters": len(memory.transcript)}
