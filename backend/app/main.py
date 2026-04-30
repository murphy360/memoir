import io
import os
import re
import base64
import logging
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4
from datetime import date, datetime
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Date, DateTime, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./memoir.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
logger = logging.getLogger("memoir.api")
AUDIO_STORAGE_DIR = Path(os.getenv("AUDIO_STORAGE_DIR", "/data/audio"))


class MemoryEntry(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    transcript: Mapped[str] = mapped_column(Text)
    event_description: Mapped[str] = mapped_column(Text)
    estimated_date_text: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    estimated_date_sort: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    emotional_tone: Mapped[str] = mapped_column(String(50), default="neutral")
    follow_up_question: Mapped[str] = mapped_column(Text)
    audio_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    audio_content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    audio_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def audio_url(self) -> Optional[str]:
        if not self.audio_filename:
            return None
        return f"/api/memories/{self.id}/audio"


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transcript: str
    event_description: str
    estimated_date_text: Optional[str]
    emotional_tone: str
    follow_up_question: str
    audio_size_bytes: Optional[int]
    audio_url: Optional[str]
    created_at: datetime


app = FastAPI(title="Memoir API", version="0.1.0")

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    AUDIO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    ensure_schema_migrations()


def ensure_schema_migrations() -> None:
    # Keep startup idempotent for SQLite without a full migration framework yet.
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(memories)")).fetchall()
        }
        if "audio_filename" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN audio_filename VARCHAR(255)"))
        if "audio_content_type" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN audio_content_type VARCHAR(100)"))
        if "audio_size_bytes" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN audio_size_bytes INTEGER"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def guess_audio_extension(filename: str, content_type: Optional[str]) -> str:
    lower_name = filename.lower()
    if "." in lower_name:
        candidate = lower_name.rsplit(".", 1)[1]
        if candidate in {"webm", "wav", "mp3", "m4a", "ogg"}:
            return f".{candidate}"

    content_map = {
        "audio/webm": ".webm",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
    }
    return content_map.get((content_type or "").lower(), ".webm")


def save_audio_file(upload: UploadFile, audio_bytes: bytes) -> tuple[str, str, int, bytes]:
    source_extension = guess_audio_extension(upload.filename or "recording.webm", upload.content_type)

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(temp_dir) / f"input{source_extension}"
        output_path = Path(temp_dir) / "output.mp3"

        input_path.write_bytes(audio_bytes)

        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-b:a",
            "128k",
            str(output_path),
        ]

        try:
            process = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail="FFmpeg is not installed on the backend container") from exc

        if process.returncode != 0 or not output_path.exists():
            error_text = (process.stderr or process.stdout or "Unknown FFmpeg error").strip()
            raise HTTPException(status_code=500, detail=f"Failed to convert audio to MP3: {error_text[:300]}")

        mp3_bytes = output_path.read_bytes()

    stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex}.mp3"
    file_path = AUDIO_STORAGE_DIR / stored_name
    file_path.write_bytes(mp3_bytes)
    return stored_name, "audio/mpeg", len(mp3_bytes), mp3_bytes


def transcribe_audio(filename: str, audio_bytes: bytes) -> str:
    allow_placeholder = os.getenv("ALLOW_PLACEHOLDER_TRANSCRIPT", "false").lower() == "true"
    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    failure_reasons: list[str] = []

    if gemini_key:
        try:
            import requests

            mime_types = ["audio/webm", "audio/webm;codecs=opus", "audio/ogg", "audio/mpeg", "audio/wav", "audio/mp4"]
            if filename and filename.lower().endswith(".wav"):
                mime_types = ["audio/wav"]
            elif filename and filename.lower().endswith(".mp3"):
                mime_types = ["audio/mpeg"]
            elif filename and filename.lower().endswith(".m4a"):
                mime_types = ["audio/mp4"]

            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
            encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")

            for mime_type in mime_types:
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": "Transcribe this audio exactly. Return plain text only."},
                                {
                                    "inline_data": {
                                        "mime_type": mime_type,
                                        "data": encoded_audio,
                                    }
                                },
                            ]
                        }
                    ]
                }

                response = requests.post(
                    endpoint,
                    params={"key": gemini_key},
                    json=payload,
                    timeout=45,
                )

                if not response.ok:
                    failure_reasons.append(f"Gemini ({mime_type}) HTTP {response.status_code}: {response.text[:180]}")
                    continue

                data = response.json()
                text_parts = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [])
                )
                text = " ".join(part.get("text", "") for part in text_parts).strip()
                if text:
                    return text

                failure_reasons.append(f"Gemini ({mime_type}) returned empty transcription")
        except Exception as exc:
            # Fall through to local placeholder if Gemini transcription fails.
            failure_reasons.append(f"Gemini exception: {str(exc)}")
            logger.exception("Gemini transcription failed")

    if allow_placeholder:
        return (
            "I remember last summer when my family and I drove our red car to the coast. "
            "It felt joyful, but I cannot remember exactly what happened on the first day."
        )

    raise HTTPException(
        status_code=502,
        detail=(
            "Transcription failed. Configure GEMINI_API_KEY to enable speech-to-text. "
            "or set ALLOW_PLACEHOLDER_TRANSCRIPT=true for demo mode. "
            f"Details: {' | '.join(failure_reasons)[:800]}"
        ),
    )


def extract_temporal_markers(transcript: str) -> tuple[str, Optional[date]]:
    lowered = transcript.lower()

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", transcript)
    if year_match:
        year = int(year_match.group(1))
        return (f"{year}", date(year, 1, 1))

    if "last summer" in lowered:
        year = datetime.utcnow().year - 1
        return ("last summer", date(year, 6, 1))

    age_match = re.search(r"when i was (\d{1,2})", lowered)
    if age_match:
        return (f"when I was {age_match.group(1)}", None)

    return ("unknown", None)


def detect_emotional_tone(transcript: str) -> str:
    lowered = transcript.lower()
    if any(word in lowered for word in ["happy", "joy", "joyful", "excited", "grateful"]):
        return "positive"
    if any(word in lowered for word in ["sad", "angry", "upset", "scared", "afraid"]):
        return "negative"
    if any(word in lowered for word in ["nostalgic", "remember", "miss"]):
        return "reflective"
    return "neutral"


def summarize_event(transcript: str) -> str:
    sentence = transcript.strip().split(".")[0].strip()
    if not sentence:
        return "Unspecified memory"
    return sentence[:180]


def generate_follow_up_question(transcript: str, event_description: str) -> str:
    lowered = transcript.lower()
    if "car" in lowered:
        return (
            "You mentioned that car memory. What is one detail about that trip "
            "that still feels vivid today?"
        )
    if "school" in lowered:
        return "What happened right after this school moment, and who was with you?"
    return (
        f"You shared: '{event_description}'. What happened just before this moment "
        "that might help place it on your timeline?"
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {"service": "memoir-api", "health": "/api/health"}


@app.get("/api/memories", response_model=list[MemoryResponse])
def list_memories(db: Session = Depends(get_db)) -> list[MemoryEntry]:
    memories = (
        db.query(MemoryEntry)
        .order_by(MemoryEntry.estimated_date_sort.is_(None), MemoryEntry.estimated_date_sort.asc(), MemoryEntry.created_at.desc())
        .all()
    )
    return memories


@app.get("/api/memories/{memory_id}/audio")
def get_memory_audio(memory_id: int, db: Session = Depends(get_db)) -> FileResponse:
    memory = db.get(MemoryEntry, memory_id)
    if not memory or not memory.audio_filename:
        raise HTTPException(status_code=404, detail="Audio not found")

    file_path = AUDIO_STORAGE_DIR / memory.audio_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing from storage")

    return FileResponse(
        path=file_path,
        media_type=(memory.audio_content_type or "application/octet-stream"),
        filename=memory.audio_filename,
    )


@app.post("/api/memories", response_model=MemoryResponse)
async def create_memory(
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> MemoryEntry:
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio payload is empty")

    audio_filename, audio_content_type, audio_size_bytes, mp3_bytes = save_audio_file(audio, audio_bytes)

    transcription_enabled = os.getenv("TRANSCRIPTION_ENABLED", "true").lower() == "true"

    if transcription_enabled:
        try:
            transcript = transcribe_audio(audio_filename, mp3_bytes)
            estimated_date_text, estimated_date_sort = extract_temporal_markers(transcript)
            emotional_tone = detect_emotional_tone(transcript)
            event_description = summarize_event(transcript)
            follow_up_question = generate_follow_up_question(transcript, event_description)
        except HTTPException as exc:
            logger.warning("Transcription failed for %s: %s", audio_filename, exc.detail)
            transcript = "Transcription failed."
            event_description = "Recorded memory (audio only)"
            estimated_date_text = "unknown"
            estimated_date_sort = datetime.utcnow().date()
            emotional_tone = "unknown"
            follow_up_question = "Transcription failed for this memory. You can still play the original audio."
    else:
        transcript = "Transcription disabled."
        event_description = "Recorded memory (audio only)"
        estimated_date_text = "recorded now"
        estimated_date_sort = datetime.utcnow().date()
        emotional_tone = "unknown"
        follow_up_question = "Transcription is turned off while testing recording and playback."

    entry = MemoryEntry(
        transcript=transcript,
        event_description=event_description,
        estimated_date_text=estimated_date_text,
        estimated_date_sort=estimated_date_sort,
        emotional_tone=emotional_tone,
        follow_up_question=follow_up_question,
        audio_filename=audio_filename,
        audio_content_type=audio_content_type,
        audio_size_bytes=audio_size_bytes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry
