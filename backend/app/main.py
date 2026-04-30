import json
import logging
import os
from pathlib import Path
from datetime import date, datetime
from typing import Optional

from fastapi import Body, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, ensure_schema_migrations, get_db
from app.models import Base, MemoryEntry, MemoryPerson, MemoryPlace, Person, PersonAlias, Place, Question
from app.schemas import (
    AddAliasRequest,
    AnswerQuestionRequest,
    CreateDirectoryEntryRequest,
    DirectoryEntryResponse,
    MemoryResponse,
    MergePersonRequest,
    QuestionResponse,
    SplitPersonRequest,
    UpdateDirectoryEntryRequest,
    UpdateMemoryRecorderRequest,
)
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
        backfill_normalized_directory(db)
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


def normalize_directory_name(value: Optional[str]) -> Optional[str]:
    candidate = (value or "").strip()
    if not candidate:
        return None
    if len(candidate) > 120:
        candidate = candidate[:120].rstrip()
    return candidate


def get_or_create_person(db: Session, raw_name: Optional[str]) -> Optional[Person]:
    name = normalize_directory_name(raw_name)
    if not name:
        return None

    # 1. Exact / case-insensitive match in the people table
    for person in db.query(Person).all():
        if person.name.casefold() == name.casefold():
            if person.name != name:
                person.name = name
            return person

    # 2. Match against known aliases — return the aliased person
    alias_row = (
        db.query(PersonAlias)
        .filter(PersonAlias.alias.ilike(name))
        .first()
    )
    if alias_row:
        return alias_row.person

    # 3. Create new person
    person = Person(name=name)
    db.add(person)
    db.flush()
    return person


def expand_person_names(db: Session, raw_name: Optional[str]) -> list[Person]:
    """Resolve a name to one or more Person objects.

    If the name is an alias shared by multiple people (e.g. 'parents'
    aliased to both Jack Murphy and Sue Murphy), all matching people are
    returned so the caller can link each one to the memory.
    """
    name = normalize_directory_name(raw_name)
    if not name:
        return []

    # 1. Direct match — always wins
    for person in db.query(Person).all():
        if person.name.casefold() == name.casefold():
            return [person]

    # 2. Alias match — may return multiple
    alias_rows = db.query(PersonAlias).filter(PersonAlias.alias.ilike(name)).all()
    if alias_rows:
        seen: set[int] = set()
        resolved: list[Person] = []
        for row in alias_rows:
            if row.person_id not in seen:
                seen.add(row.person_id)
                resolved.append(row.person)
        return resolved

    # 3. Fall through — create new person
    person = Person(name=name)
    db.add(person)
    db.flush()
    return [person]


def get_or_create_place(db: Session, raw_name: Optional[str]) -> Optional[Place]:
    name = normalize_directory_name(raw_name)
    if not name:
        return None

    for place in db.query(Place).all():
        if place.name.casefold() == name.casefold():
            if place.name != name:
                place.name = name
            return place

    place = Place(name=name)
    db.add(place)
    db.flush()
    return place


def sync_memory_people(db: Session, memory: MemoryEntry, names: list[str]) -> None:
    ordered_people: list[Person] = []
    seen_keys: set[str] = set()

    for raw_name in names:
        for person in expand_person_names(db, raw_name):
            key = person.name.casefold()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            ordered_people.append(person)

    existing_links = {link.person_id: link for link in memory.people_links}
    desired_ids = {person.id for person in ordered_people}

    for link in list(memory.people_links):
        if link.person_id not in desired_ids:
            memory.people_links.remove(link)
            db.delete(link)

    for person in ordered_people:
        if person.id not in existing_links:
            memory.people_links.append(MemoryPerson(person_id=person.id, role="mentioned"))

    memory.people_json = json.dumps([person.name for person in ordered_people])


def sync_memory_places(db: Session, memory: MemoryEntry, names: list[str]) -> None:
    ordered_places: list[Place] = []
    seen_keys: set[str] = set()

    for raw_name in names:
        place = get_or_create_place(db, raw_name)
        if not place:
            continue
        key = place.name.casefold()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        ordered_places.append(place)

    existing_links = {link.place_id: link for link in memory.place_links}
    desired_ids = {place.id for place in ordered_places}

    for link in list(memory.place_links):
        if link.place_id not in desired_ids:
            memory.place_links.remove(link)
            db.delete(link)

    for place in ordered_places:
        if place.id not in existing_links:
            memory.place_links.append(MemoryPlace(place_id=place.id))

    memory.locations_json = json.dumps([place.name for place in ordered_places])


def assign_recorder_person(db: Session, memory: MemoryEntry, raw_name: Optional[str]) -> None:
    person = get_or_create_person(db, raw_name)
    if not person:
        memory.recorder_person = None
        memory.recorder_person_id = None
        memory.recorder_name = None
        return

    memory.recorder_person = person
    memory.recorder_person_id = person.id
    memory.recorder_name = person.name


def backfill_normalized_directory(db: Session) -> None:
    for memory in db.query(MemoryEntry).all():
        recorder_name = memory.recorder_name
        if not recorder_name and memory.recorder_person:
            recorder_name = memory.recorder_person.name
        assign_recorder_person(db, memory, recorder_name)
        sync_memory_people(db, memory, memory.referenced_people)
        sync_memory_places(db, memory, memory.referenced_locations)

    db.commit()


def build_directory_response(
    name: str,
    item_id: int,
    memory_count: int,
    aliases: Optional[list[str]] = None,
) -> DirectoryEntryResponse:
    return DirectoryEntryResponse(
        id=item_id,
        name=name,
        memory_count=memory_count,
        aliases=aliases or [],
    )


def list_people_directory(db: Session) -> list[DirectoryEntryResponse]:
    memories = db.query(MemoryEntry).all()
    counts: dict[int, set[int]] = {}

    for memory in memories:
        if memory.recorder_person_id is not None:
            counts.setdefault(memory.recorder_person_id, set()).add(memory.id)
        for link in memory.people_links:
            counts.setdefault(link.person_id, set()).add(memory.id)

    people = db.query(Person).order_by(Person.name.asc()).all()
    return [
        build_directory_response(
            person.name,
            person.id,
            len(counts.get(person.id, set())),
            [a.alias for a in person.aliases],
        )
        for person in people
    ]


def list_places_directory(db: Session) -> list[DirectoryEntryResponse]:
    counts: dict[int, set[int]] = {}

    for memory in db.query(MemoryEntry).all():
        for link in memory.place_links:
            counts.setdefault(link.place_id, set()).add(memory.id)

    places = db.query(Place).order_by(Place.name.asc()).all()
    return [
        build_directory_response(place.name, place.id, len(counts.get(place.id, set())))
        for place in places
    ]


def update_memory_json_from_links(memory: MemoryEntry) -> None:
    memory.people_json = json.dumps(memory.referenced_people)
    memory.locations_json = json.dumps(memory.referenced_locations)


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
        .order_by(MemoryEntry.estimated_date_sort.is_(None), MemoryEntry.estimated_date_sort.asc(), MemoryEntry.date_recorded.desc().nulls_last(), MemoryEntry.created_at.desc())
        .all()
    )
    return memories


@app.get("/api/people", response_model=list[DirectoryEntryResponse])
def list_people(db: Session = Depends(get_db)) -> list[DirectoryEntryResponse]:
    return list_people_directory(db)


@app.post("/api/people", response_model=DirectoryEntryResponse)
def create_person(body: CreateDirectoryEntryRequest, db: Session = Depends(get_db)) -> DirectoryEntryResponse:
    person = get_or_create_person(db, body.name)
    if not person:
        raise HTTPException(status_code=400, detail="Person name is required")
    db.commit()
    return build_directory_response(person.name, person.id, 0)


@app.patch("/api/people/{person_id}", response_model=DirectoryEntryResponse)
def rename_person(
    person_id: int,
    body: UpdateDirectoryEntryRequest,
    db: Session = Depends(get_db),
) -> DirectoryEntryResponse:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    name = normalize_directory_name(body.name)
    if not name:
        raise HTTPException(status_code=400, detail="Person name is required")

    for existing in db.query(Person).all():
        if existing.id != person.id and existing.name.casefold() == name.casefold():
            raise HTTPException(status_code=409, detail="Person name already exists")

    person.name = name
    for memory in db.query(MemoryEntry).all():
        if memory.recorder_person_id == person.id:
            memory.recorder_name = person.name
        if any(link.person_id == person.id for link in memory.people_links):
            memory.people_json = json.dumps(memory.referenced_people)

    db.commit()
    return build_directory_response(person.name, person.id, len({
        memory.id
        for memory in db.query(MemoryEntry).all()
        if memory.recorder_person_id == person.id or any(link.person_id == person.id for link in memory.people_links)
    }))


@app.post("/api/people/{person_id}/merge", response_model=DirectoryEntryResponse)
def merge_person(
    person_id: int,
    body: MergePersonRequest,
    db: Session = Depends(get_db),
) -> DirectoryEntryResponse:
    source = db.get(Person, person_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source person not found")

    target = db.get(Person, body.into_person_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target person not found")

    if source.id == target.id:
        raise HTTPException(status_code=400, detail="Cannot merge a person into themselves")

    for memory in db.query(MemoryEntry).all():
        if memory.recorder_person_id == source.id:
            assign_recorder_person(db, memory, target.name)

        already_linked = any(link.person_id == target.id for link in memory.people_links)
        has_source_link = any(link.person_id == source.id for link in memory.people_links)

        if has_source_link:
            for link in list(memory.people_links):
                if link.person_id == source.id:
                    memory.people_links.remove(link)
                    db.delete(link)
            if not already_linked:
                memory.people_links.append(MemoryPerson(person_id=target.id, role="mentioned"))
            memory.people_json = json.dumps(memory.referenced_people)

    db.delete(source)
    db.commit()
    db.refresh(target)

    updated = next((p for p in list_people_directory(db) if p.id == target.id), None)
    if updated:
        return updated
    return build_directory_response(target.name, target.id, 0)


@app.post("/api/people/{person_id}/split", response_model=list[DirectoryEntryResponse])
def split_person(
    person_id: int,
    body: SplitPersonRequest,
    db: Session = Depends(get_db),
) -> list[DirectoryEntryResponse]:
    source = db.get(Person, person_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source person not found")

    new_names = [normalize_directory_name(n) for n in body.new_names]
    new_names = [n for n in new_names if n]
    if not new_names:
        raise HTTPException(status_code=400, detail="At least one new name is required")

    source_name = source.name

    # Create (or locate) each new person
    new_people: list[Person] = []
    for name in new_names:
        p = get_or_create_person(db, name)
        if p:
            new_people.append(p)
    db.flush()

    # Reassign memory links from source to all new people
    for memory in db.query(MemoryEntry).all():
        if memory.recorder_person_id == source.id:
            # Recorder is ambiguous after split — clear it
            memory.recorder_person = None
            memory.recorder_person_id = None
            memory.recorder_name = None

        has_source_link = any(link.person_id == source.id for link in memory.people_links)
        if has_source_link:
            for link in list(memory.people_links):
                if link.person_id == source.id:
                    memory.people_links.remove(link)
                    db.delete(link)
            for new_person in new_people:
                already_linked = any(link.person_id == new_person.id for link in memory.people_links)
                if not already_linked:
                    memory.people_links.append(MemoryPerson(person_id=new_person.id, role="mentioned"))
            memory.people_json = json.dumps(memory.referenced_people)

    # Add the old name as an alias on each new person
    if body.keep_alias:
        for new_person in new_people:
            already_has_alias = any(
                a.alias.casefold() == source_name.casefold() for a in new_person.aliases
            )
            if not already_has_alias:
                db.add(PersonAlias(person_id=new_person.id, alias=source_name))

    db.delete(source)
    db.commit()

    return list_people_directory(db)


@app.post("/api/people/{person_id}/aliases", response_model=DirectoryEntryResponse)
def add_person_alias(
    person_id: int,
    body: AddAliasRequest,
    db: Session = Depends(get_db),
) -> DirectoryEntryResponse:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    alias = normalize_directory_name(body.alias)
    if not alias:
        raise HTTPException(status_code=400, detail="Alias text is required")

    # Check alias isn't already a person name
    for p in db.query(Person).all():
        if p.id != person_id and p.name.casefold() == alias.casefold():
            raise HTTPException(status_code=409, detail="That name belongs to another person")

    # Check not already present for this person
    if any(a.alias.casefold() == alias.casefold() for a in person.aliases):
        db.commit()  # no-op, just return current state
    else:
        db.add(PersonAlias(person_id=person_id, alias=alias))
        db.commit()
        db.refresh(person)

    directory = list_people_directory(db)
    entry = next((e for e in directory if e.id == person_id), None)
    return entry or build_directory_response(person.name, person.id, 0)


@app.delete("/api/people/{person_id}/aliases/{alias}")
def remove_person_alias(
    person_id: int,
    alias: str,
    db: Session = Depends(get_db),
) -> dict:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    row = next(
        (a for a in person.aliases if a.alias.casefold() == alias.casefold()),
        None,
    )
    if row:
        db.delete(row)
        db.commit()

    return {"status": "deleted", "alias": alias, "person_id": person_id}


@app.delete("/api/people/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db)) -> dict:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    for memory in db.query(MemoryEntry).all():
        if memory.recorder_person_id == person.id:
            memory.recorder_person = None
            memory.recorder_person_id = None
            memory.recorder_name = None

        removed = False
        for link in list(memory.people_links):
            if link.person_id == person.id:
                memory.people_links.remove(link)
                db.delete(link)
                removed = True
        if removed:
            update_memory_json_from_links(memory)

    db.delete(person)
    db.commit()
    return {"status": "deleted", "person_id": person_id}


@app.get("/api/places", response_model=list[DirectoryEntryResponse])
def list_places(db: Session = Depends(get_db)) -> list[DirectoryEntryResponse]:
    return list_places_directory(db)


@app.post("/api/places", response_model=DirectoryEntryResponse)
def create_place(body: CreateDirectoryEntryRequest, db: Session = Depends(get_db)) -> DirectoryEntryResponse:
    place = get_or_create_place(db, body.name)
    if not place:
        raise HTTPException(status_code=400, detail="Place name is required")
    db.commit()
    return build_directory_response(place.name, place.id, 0)


@app.patch("/api/places/{place_id}", response_model=DirectoryEntryResponse)
def rename_place(
    place_id: int,
    body: UpdateDirectoryEntryRequest,
    db: Session = Depends(get_db),
) -> DirectoryEntryResponse:
    place = db.get(Place, place_id)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    name = normalize_directory_name(body.name)
    if not name:
        raise HTTPException(status_code=400, detail="Place name is required")

    for existing in db.query(Place).all():
        if existing.id != place.id and existing.name.casefold() == name.casefold():
            raise HTTPException(status_code=409, detail="Place name already exists")

    place.name = name
    for memory in db.query(MemoryEntry).all():
        if any(link.place_id == place.id for link in memory.place_links):
            memory.locations_json = json.dumps(memory.referenced_locations)

    db.commit()
    return build_directory_response(place.name, place.id, len({
        memory.id for memory in db.query(MemoryEntry).all() if any(link.place_id == place.id for link in memory.place_links)
    }))


@app.delete("/api/places/{place_id}")
def delete_place(place_id: int, db: Session = Depends(get_db)) -> dict:
    place = db.get(Place, place_id)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    for memory in db.query(MemoryEntry).all():
        removed = False
        for link in list(memory.place_links):
            if link.place_id == place.id:
                memory.place_links.remove(link)
                db.delete(link)
                removed = True
        if removed:
            update_memory_json_from_links(memory)

    db.delete(place)
    db.commit()
    return {"status": "deleted", "place_id": place_id}


def analyze_memory_audio(
    filename: str,
    audio_bytes: bytes,
    transcription_enabled: bool,
) -> tuple[str, str, Optional[date], str, str, str, MemoryMetadata]:
    if transcription_enabled:
        try:
            transcript = transcribe_audio(filename, audio_bytes)
            metadata = extract_metadata_with_gemini_function_call(transcript)
            if metadata is None:
                metadata = fallback_metadata_from_transcript(transcript)

            estimated_date_text = metadata.date_text
            estimated_date_sort = metadata.sort_date
            emotional_tone = detect_emotional_tone(transcript)
            event_description = summarize_event(transcript)
            follow_up_question = generate_follow_up_question(transcript, event_description, metadata)
            return (
                transcript,
                event_description,
                estimated_date_sort,
                estimated_date_text,
                emotional_tone,
                follow_up_question,
                metadata,
            )
        except HTTPException as exc:
            logger.warning("Transcription failed for %s: %s", filename, exc.detail)
            return (
                "Transcription failed.",
                "Recorded memory (audio only)",
                None,
                "unknown",
                "unknown",
                "Transcription failed for this memory. You can still play the original audio.",
                MemoryMetadata(),
            )

    now = datetime.utcnow()
    return (
        "Transcription disabled.",
        "Recorded memory (audio only)",
        now.date(),
        "recorded now",
        "unknown",
        "Transcription is turned off while testing recording and playback.",
        MemoryMetadata(
            date_text="recorded now",
            date_precision="day",
            sort_date=now.date(),
            date_year=now.year,
            date_month=now.month,
            date_day=now.day,
        ),
    )


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

    (
        transcript,
        event_description,
        estimated_date_sort,
        estimated_date_text,
        emotional_tone,
        follow_up_question,
        metadata,
    ) = analyze_memory_audio(audio_filename, mp3_bytes, transcription_enabled)

    entry = MemoryEntry(
        transcript=transcript,
        event_description=event_description,
        estimated_date_text=estimated_date_text,
        estimated_date_sort=estimated_date_sort,
        date_recorded=date.today(),
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
    db.flush()
    assign_recorder_person(db, entry, metadata.recorder_name)
    sync_memory_people(db, entry, metadata.people)
    sync_memory_places(db, entry, metadata.locations)
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


@app.post("/api/memories/{memory_id}/reanalyze", response_model=MemoryResponse)
def reanalyze_memory(memory_id: int, db: Session = Depends(get_db)) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    if not memory.audio_filename:
        raise HTTPException(status_code=400, detail="Memory has no stored audio to reanalyze")

    file_path = AUDIO_STORAGE_DIR / memory.audio_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing from storage")

    mp3_bytes = file_path.read_bytes()
    if not mp3_bytes:
        raise HTTPException(status_code=400, detail="Stored audio is empty")

    transcription_enabled = os.getenv("TRANSCRIPTION_ENABLED", "true").lower() == "true"
    (
        transcript,
        event_description,
        estimated_date_sort,
        estimated_date_text,
        emotional_tone,
        follow_up_question,
        metadata,
    ) = analyze_memory_audio(memory.audio_filename, mp3_bytes, transcription_enabled)

    memory.transcript = transcript
    memory.event_description = event_description
    memory.estimated_date_sort = estimated_date_sort
    memory.estimated_date_text = estimated_date_text
    memory.emotional_tone = emotional_tone
    memory.follow_up_question = follow_up_question
    memory.date_precision = metadata.date_precision
    memory.date_year = metadata.date_year
    memory.date_month = metadata.date_month
    memory.date_day = metadata.date_day
    memory.date_decade = metadata.date_decade
    if not memory.recorder_person_id and not memory.recorder_name:
        assign_recorder_person(db, memory, metadata.recorder_name)
    sync_memory_people(db, memory, metadata.people)
    sync_memory_places(db, memory, metadata.locations)

    db.query(Question).filter(
        Question.source_memory_id == memory.id,
        Question.status == "pending",
    ).delete(synchronize_session=False)

    if transcription_enabled and transcript not in ("Transcription failed.", "Transcription disabled."):
        for q_text in generate_questions_from_memory(transcript, event_description, metadata):
            db.add(Question(text=q_text, source_memory_id=memory.id, status="pending"))

    db.commit()
    db.refresh(memory)
    return memory


@app.patch("/api/memories/{memory_id}/recorder", response_model=MemoryResponse)
def update_memory_recorder(
    memory_id: int,
    body: UpdateMemoryRecorderRequest = Body(...),
    db: Session = Depends(get_db),
) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    if body.person_id is not None:
        person = db.get(Person, body.person_id)
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        assign_recorder_person(db, memory, person.name)
    else:
        assign_recorder_person(db, memory, body.recorder_name)

    db.commit()
    db.refresh(memory)
    return memory


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_db)) -> dict:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    file_path = AUDIO_STORAGE_DIR / memory.audio_filename if memory.audio_filename else None
    db.query(Question).filter(Question.source_memory_id == memory.id).delete(synchronize_session=False)
    db.query(Question).filter(Question.answer_memory_id == memory.id).update(
        {Question.answer_memory_id: None},
        synchronize_session=False,
    )
    db.query(MemoryPerson).filter(MemoryPerson.memory_id == memory.id).delete(synchronize_session=False)
    db.query(MemoryPlace).filter(MemoryPlace.memory_id == memory.id).delete(synchronize_session=False)
    db.delete(memory)
    db.commit()

    if file_path and file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            logger.warning("Could not delete audio file for memory %s", memory_id)

    return {"status": "deleted", "memory_id": memory_id}


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
