"""The normalisation job: original recording in, MP3 out, both kept."""

import tempfile
from pathlib import Path

from app.blobs.store import BlobStore
from app.capture import audio
from app.core.settings import get_settings
from app.domain.memories import Memory
from app.jobs import queue
from app.jobs.registry import JobContext, PermanentError, handler


@handler("capture.normalize_audio")
def normalize_audio(ctx: JobContext, payload: dict) -> dict:
    memory = ctx.session.get(Memory, payload["memory_id"])
    if memory is None or memory.original_audio_sha256 is None:
        raise PermanentError("no recording to normalise")
    store = BlobStore(get_settings().blob_root)
    source = store.path(memory.original_audio_sha256)
    store.verify(memory.original_audio_sha256)
    ctx.progress(step="normalising")
    with tempfile.TemporaryDirectory() as tmp:
        result = audio.normalise(source, Path(tmp) / "out.mp3")
        if result.ok:
            with result.mp3.open("rb") as f:
                mp3 = store.put(
                    ctx.session, iter(lambda: f.read(1 << 20), b""), "audio/mpeg"
                )
            memory.audio_sha256 = mp3.sha256
            memory.audio_state = "normalised"
            memory.audio_seconds = result.seconds
        else:
            # The original stays the recording; transcription can still use it.
            memory.audio_state = "not_normalised"
            memory.audio_seconds = audio.duration(source)
    ctx.session.commit()
    # Next: words. Transcription runs on the MP3, or on the original when there is none.
    queue.enqueue(
        ctx.session,
        "analysis.transcribe",
        {"memory_id": memory.id},
        idempotency_key=f"transcribe:{memory.id}",
    )
    return {
        "state": memory.audio_state,
        "problem": result.problem,
        "seconds": memory.audio_seconds,
    }
