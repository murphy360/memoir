import json
import logging
import os
from pathlib import Path
from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, ensure_schema_migrations, get_db
from app.models import Base, MemoryEntry, Question
from app.schemas import AnswerQuestionRequest, MemoryResponse, QuestionResponse
from app.services.audio_storage import save_audio_file
from app.services.gemini_client import (
    extract_metadata_with_gemini_function_call,
    transcribe_audio,
)
from app.services.memory_analysis import (
    MemoryMetadata,
    detect_emotional_tone,
    fallback_metadata_from_transcript,
    generate_follow_up_question,
    generate_questions_from_memory,
    summarize_event,
)

logger = logging.getLogger("memoir.api")
AUDIO_STORAGE_DIR = Path(os.getenv("AUDIO_STORAGE_DIR", "/data/audio"))


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
    db = SessionLocal()
    try:
        seed_initial_questions(db)
    finally:
        db.close()


SEED_QUESTIONS = [
    "What is your name, where are you recording from, and when is this memory from (day, month, year, or decade)?",
    "When and where were you born? If you are unsure of the date, tell us the closest year or decade.",
    "Tell me about your family — who are the most important people in your life?",
]


def seed_initial_questions(db: Session) -> None:
    """Insert starter questions the first time the app launches."""
    if db.query(Question).count() == 0:
        for q_text in SEED_QUESTIONS:
            db.add(Question(text=q_text, status="pending"))
        db.commit()


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

    audio_filename, audio_content_type, audio_size_bytes, mp3_bytes = save_audio_file(audio, audio_bytes, AUDIO_STORAGE_DIR)

    transcription_enabled = os.getenv("TRANSCRIPTION_ENABLED", "true").lower() == "true"

    if transcription_enabled:
        try:
            transcript = transcribe_audio(audio_filename, mp3_bytes)
            metadata = extract_metadata_with_gemini_function_call(transcript)
            if metadata is None:
                metadata = fallback_metadata_from_transcript(transcript)

            estimated_date_text = metadata.date_text
            estimated_date_sort = metadata.sort_date
            emotional_tone = detect_emotional_tone(transcript)
            event_description = summarize_event(transcript)
            follow_up_question = generate_follow_up_question(transcript, event_description, metadata)
        except HTTPException as exc:
            logger.warning("Transcription failed for %s: %s", audio_filename, exc.detail)
            transcript = "Transcription failed."
            event_description = "Recorded memory (audio only)"
            estimated_date_text = "unknown"
            estimated_date_sort = None
            emotional_tone = "unknown"
            follow_up_question = "Transcription failed for this memory. You can still play the original audio."
            metadata = MemoryMetadata()
    else:
        transcript = "Transcription disabled."
        event_description = "Recorded memory (audio only)"
        estimated_date_text = "recorded now"
        estimated_date_sort = datetime.utcnow().date()
        emotional_tone = "unknown"
        follow_up_question = "Transcription is turned off while testing recording and playback."
        metadata = MemoryMetadata(
            date_text="recorded now",
            date_precision="day",
            sort_date=datetime.utcnow().date(),
            date_year=datetime.utcnow().year,
            date_month=datetime.utcnow().month,
            date_day=datetime.utcnow().day,
        )

    entry = MemoryEntry(
        transcript=transcript,
        event_description=event_description,
        estimated_date_text=estimated_date_text,
        estimated_date_sort=estimated_date_sort,
        date_precision=metadata.date_precision,
        date_year=metadata.date_year,
        date_month=metadata.date_month,
        date_day=metadata.date_day,
        date_decade=metadata.date_decade,
        recorder_name=metadata.recorder_name,
        people_json=json.dumps(metadata.people),
        locations_json=json.dumps(metadata.locations),
        emotional_tone=emotional_tone,
        follow_up_question=follow_up_question,
        audio_filename=audio_filename,
        audio_content_type=audio_content_type,
        audio_size_bytes=audio_size_bytes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    if transcription_enabled and transcript not in ("Transcription failed.", "Transcription disabled."):
        try:
            for q_text in generate_questions_from_memory(transcript, event_description, metadata):
                db.add(Question(text=q_text, source_memory_id=entry.id, status="pending"))
            db.commit()
        except Exception as exc:
            logger.warning("Could not generate questions for memory %s: %s", entry.id, exc)

    return entry


@app.get("/api/questions", response_model=list[QuestionResponse])
def list_questions(db: Session = Depends(get_db)) -> list[Question]:
    return (
        db.query(Question)
        .filter(Question.status == "pending")
        .order_by(Question.created_at.asc())
        .all()
    )


@app.post("/api/questions/{question_id}/answer")
def answer_question(
    question_id: int,
    body: AnswerQuestionRequest,
    db: Session = Depends(get_db),
) -> dict:
    question = db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    question.status = "answered"
    question.answer_memory_id = body.answer_memory_id
    db.commit()
    return {"status": "answered"}


@app.post("/api/questions/{question_id}/dismiss")
def dismiss_question(question_id: int, db: Session = Depends(get_db)) -> dict:
    question = db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    question.status = "dismissed"
    db.commit()
    return {"status": "dismissed"}
