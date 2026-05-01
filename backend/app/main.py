import dataclasses
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from datetime import date, datetime
from typing import Optional

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, ensure_schema_migrations, get_db
from app.models import Asset, Base, EventAsset, LifeEvent, LifePeriod, MemoryEntry, MemoryPerson, MemoryPlace, Person, PersonAlias, Place, Question, Setting
from app.schemas import (
    AssetResponse,
    AddAliasRequest,
    AnswerQuestionRequest,
    CreateLifeEventRequest,
    CreateLifePeriodRequest,
    CreateDirectoryEntryRequest,
    DirectoryEntryResponse,
    LifeEventResponse,
    LifePeriodResponse,
    MergeLifeEventRequest,
    LinkAssetToEventRequest,
    MemoryResponse,
    MergePersonRequest,
    QuestionResponse,
    SettingsResponse,
    SplitPersonRequest,
    UpdateDirectoryEntryRequest,
    UpdateMemoryRecorderRequest,
    UpdateSettingRequest,
)
from app.services.audio_storage import save_audio_file
from app.services.document_storage import save_document_file
from app.services.gemini_client import (
    extract_metadata_with_gemini_function_call,
    generate_research_questions,
    research_memory_details,
    suggest_date_from_research,
    transcribe_audio,
)
from app.services.gemini_client import extract_text_from_document
from app.services.memory_analysis import (
    MemoryMetadata,
    build_sort_date,
    detect_emotional_tone,
    fallback_metadata_from_transcript,
    generate_follow_up_question,
    generate_questions_from_memory,
    summarize_event,
)

logger = logging.getLogger("memoir.api")
AUDIO_STORAGE_DIR = Path(os.getenv("AUDIO_STORAGE_DIR", "/data/audio"))
DOCUMENT_STORAGE_DIR = Path(os.getenv("DOCUMENT_STORAGE_DIR", "/data/documents"))


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
    logger.info("=== APP STARTUP ===")
    logger.info("Registered models: %s", [t for t in Base.metadata.tables.keys()])
    logger.info("Creating tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tables after create_all: %s", [t for t in Base.metadata.tables.keys()])
    AUDIO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Running schema migrations...")
    ensure_schema_migrations()
    logger.info("Schema migrations complete")
    db = SessionLocal()
    try:
        backfill_normalized_directory(db)
        backfill_life_hierarchy(db)
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


def normalize_question_text(value: Optional[str]) -> str:
    return " ".join((value or "").split()).strip().casefold()


def add_unique_pending_questions(db: Session, question_texts: list[str], source_memory_id: int) -> None:
    existing_pending = db.query(Question).filter(Question.status == "pending").all()
    seen_pending = {
        normalized
        for question in existing_pending
        for normalized in [normalize_question_text(question.text)]
        if normalized
    }

    for q_text in question_texts:
        normalized = normalize_question_text(q_text)
        if not normalized or normalized in seen_pending:
            continue
        db.add(Question(text=q_text, source_memory_id=source_memory_id, status="pending"))
        seen_pending.add(normalized)


def normalize_directory_name(value: Optional[str]) -> Optional[str]:
    candidate = (value or "").strip()
    if not candidate:
        return None
    if len(candidate) > 120:
        candidate = candidate[:120].rstrip()
    return candidate


def normalize_period_title(value: Optional[str]) -> Optional[str]:
    title = normalize_directory_name(value)
    if not title:
        return None
    if len(title) > 160:
        title = title[:160].rstrip()
    return title


def slugify_period_title(value: str) -> str:
    compact = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return compact[:180] or "period"


def unique_period_slug(db: Session, title: str, existing_id: Optional[int] = None) -> str:
    base = slugify_period_title(title)
    candidate = base
    suffix = 2
    while True:
        match = db.query(LifePeriod).filter(LifePeriod.slug == candidate).first()
        if not match or (existing_id is not None and match.id == existing_id):
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def build_period_response(period: LifePeriod) -> LifePeriodResponse:
    return LifePeriodResponse(
        id=period.id,
        title=period.title,
        slug=period.slug,
        start_date_text=period.start_date_text,
        end_date_text=period.end_date_text,
        summary=period.summary,
        event_count=len(period.events),
        asset_count=len(period.assets),
        created_at=period.created_at,
        updated_at=period.updated_at,
    )


def build_event_response(event: LifeEvent) -> LifeEventResponse:
    legacy_memory = event.legacy_memory

    return LifeEventResponse(
        id=event.id,
        period_id=event.period_id,
        title=event.title,
        description=event.description,
        event_date_text=event.event_date_text,
        date_precision=event.date_precision,
        date_year=event.date_year,
        date_month=event.date_month,
        date_day=event.date_day,
        date_decade=event.date_decade,
        legacy_audio_url=(legacy_memory.audio_url if legacy_memory else None),
        legacy_audio_size_bytes=(legacy_memory.audio_size_bytes if legacy_memory else None),
        linked_asset_count=len(event.linked_assets),
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def build_asset_response(asset: Asset) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        period_id=asset.period_id,
        kind=asset.kind,
        original_filename=asset.original_filename,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        playback_url=(asset.download_url if (asset.content_type or "").startswith("audio/") else None),
        text_excerpt=asset.text_excerpt,
        notes=asset.notes,
        download_url=asset.download_url,
        linked_event_ids=[link.event_id for link in asset.event_links],
        created_at=asset.created_at,
    )


def ensure_event_asset_link(db: Session, event: LifeEvent, asset: Asset, relation_type: str = "evidence") -> None:
    exists = any(link.asset_id == asset.id for link in event.linked_assets)
    if not exists:
        db.add(EventAsset(event_id=event.id, asset_id=asset.id, relation_type=relation_type[:30]))


def sync_life_hierarchy_for_memory(db: Session, memory: MemoryEntry) -> None:
    period = get_or_create_period_for_memory(db, memory)

    event = (
        db.query(LifeEvent)
        .filter(LifeEvent.legacy_memory_id == memory.id)
        .first()
    )
    if not event:
        event_title = (memory.event_description or "").strip() or f"Memory {memory.id}"
        if len(event_title) > 180:
            event_title = event_title[:180].rstrip()

        event = LifeEvent(
            period_id=period.id,
            title=event_title,
            description=memory.transcript,
            event_date_text=memory.estimated_date_text,
            event_date_sort=memory.estimated_date_sort,
            date_precision=memory.date_precision,
            date_year=memory.date_year,
            date_month=memory.date_month,
            date_day=memory.date_day,
            date_decade=memory.date_decade,
            legacy_memory_id=memory.id,
        )
        db.add(event)
        db.flush()
    else:
        if event.period_id is None:
            event.period_id = period.id

    if memory.audio_filename:
        audio_asset = (
            db.query(Asset)
            .filter(Asset.legacy_memory_id == memory.id, Asset.kind == "audio")
            .first()
        )
        if not audio_asset:
            audio_asset = Asset(
                period_id=period.id,
                kind="audio",
                storage_filename=memory.audio_filename,
                original_filename=memory.audio_filename,
                content_type=memory.audio_content_type,
                size_bytes=memory.audio_size_bytes,
                text_excerpt=(memory.transcript or "").strip()[:1200] or None,
                notes=f"Audio recording with transcript from legacy memory {memory.id}.",
                legacy_memory_id=memory.id,
            )
            db.add(audio_asset)
            db.flush()
        else:
            if audio_asset.period_id is None:
                audio_asset.period_id = period.id
            if not audio_asset.text_excerpt and memory.transcript:
                audio_asset.text_excerpt = memory.transcript[:1200]

        ensure_event_asset_link(db, event, audio_asset, relation_type="recording")

    if memory.document_filename:
        asset_kind = "photo" if (memory.document_content_type or "").startswith("image/") else "document"
        document_asset = (
            db.query(Asset)
            .filter(Asset.legacy_memory_id == memory.id, Asset.kind == asset_kind)
            .first()
        )
        if not document_asset:
            document_asset = Asset(
                period_id=period.id,
                kind=asset_kind,
                storage_filename=memory.document_filename,
                original_filename=memory.document_original_filename,
                content_type=memory.document_content_type,
                size_bytes=memory.document_size_bytes,
                text_excerpt=(memory.transcript or "").strip()[:1200] or None,
                notes=f"Backfilled from legacy memory {memory.id}.",
                legacy_memory_id=memory.id,
            )
            db.add(document_asset)
            db.flush()
        else:
            if document_asset.period_id is None:
                document_asset.period_id = period.id

        ensure_event_asset_link(db, event, document_asset)


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


def get_or_create_period_for_memory(db: Session, memory: MemoryEntry) -> LifePeriod:
    if memory.date_year:
        title = f"{memory.date_year}"
        slug = f"year-{memory.date_year}"
        start_sort = date(memory.date_year, 1, 1)
        end_sort = date(memory.date_year, 12, 31)
        start_text = str(memory.date_year)
        end_text = str(memory.date_year)
    elif memory.date_decade:
        decade_start = memory.date_decade
        decade_end = memory.date_decade + 9
        title = f"{decade_start}s"
        slug = f"decade-{decade_start}"
        start_sort = date(decade_start, 1, 1)
        end_sort = date(decade_end, 12, 31)
        start_text = str(decade_start)
        end_text = str(decade_end)
    elif memory.estimated_date_sort:
        inferred_year = memory.estimated_date_sort.year
        title = f"{inferred_year}"
        slug = f"year-{inferred_year}"
        start_sort = date(inferred_year, 1, 1)
        end_sort = date(inferred_year, 12, 31)
        start_text = str(inferred_year)
        end_text = str(inferred_year)
    else:
        title = "Undated"
        slug = "undated"
        start_sort = None
        end_sort = None
        start_text = "unknown"
        end_text = "unknown"

    period = db.query(LifePeriod).filter(LifePeriod.slug == slug).first()
    if period:
        return period

    period = LifePeriod(
        title=title,
        slug=unique_period_slug(db, slug),
        start_date_text=start_text,
        end_date_text=end_text,
        start_sort=start_sort,
        end_sort=end_sort,
        summary="Auto-created from existing memories.",
    )
    db.add(period)
    db.flush()
    return period


def backfill_life_hierarchy(db: Session) -> None:
    memories = db.query(MemoryEntry).order_by(MemoryEntry.created_at.asc()).all()

    for memory in memories:
        sync_life_hierarchy_for_memory(db, memory)

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


@app.get("/api/periods", response_model=list[LifePeriodResponse])
def list_periods(db: Session = Depends(get_db)) -> list[LifePeriodResponse]:
    periods = db.query(LifePeriod).order_by(LifePeriod.start_sort.asc().nulls_last(), LifePeriod.created_at.asc()).all()
    return [build_period_response(period) for period in periods]


@app.post("/api/periods", response_model=LifePeriodResponse)
def create_period(body: CreateLifePeriodRequest, db: Session = Depends(get_db)) -> LifePeriodResponse:
    title = normalize_period_title(body.title)
    if not title:
        raise HTTPException(status_code=400, detail="Period title is required")

    period = LifePeriod(
        title=title,
        slug=unique_period_slug(db, title),
        start_date_text=body.start_date_text,
        end_date_text=body.end_date_text,
        summary=body.summary,
    )
    db.add(period)
    db.commit()
    db.refresh(period)
    return build_period_response(period)


@app.get("/api/periods/{period_id}/events", response_model=list[LifeEventResponse])
def list_period_events(period_id: int, db: Session = Depends(get_db)) -> list[LifeEventResponse]:
    period = db.get(LifePeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    events = (
        db.query(LifeEvent)
        .filter(LifeEvent.period_id == period_id)
        .order_by(LifeEvent.event_date_sort.is_(None), LifeEvent.event_date_sort.asc(), LifeEvent.created_at.asc())
        .all()
    )
    return [build_event_response(event) for event in events]


@app.post("/api/events", response_model=LifeEventResponse)
def create_event(body: CreateLifeEventRequest, db: Session = Depends(get_db)) -> LifeEventResponse:
    title = normalize_directory_name(body.title)
    if not title:
        raise HTTPException(status_code=400, detail="Event title is required")

    if body.period_id is not None and not db.get(LifePeriod, body.period_id):
        raise HTTPException(status_code=404, detail="Period not found")

    event = LifeEvent(
        period_id=body.period_id,
        title=title,
        description=body.description,
        event_date_text=body.event_date_text,
        date_precision=body.date_precision,
        date_year=body.date_year,
        date_month=body.date_month,
        date_day=body.date_day,
        date_decade=body.date_decade,
        event_date_sort=build_sort_date(
            body.date_precision,
            body.date_year,
            body.date_month,
            body.date_day,
            body.date_decade,
        ),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return build_event_response(event)


@app.get("/api/events", response_model=list[LifeEventResponse])
def list_events(period_id: Optional[int] = None, db: Session = Depends(get_db)) -> list[LifeEventResponse]:
    query = db.query(LifeEvent)
    if period_id is not None:
        query = query.filter(LifeEvent.period_id == period_id)
    events = query.order_by(LifeEvent.event_date_sort.is_(None), LifeEvent.event_date_sort.asc(), LifeEvent.created_at.asc()).all()
    return [build_event_response(event) for event in events]


@app.post("/api/events/{event_id}/merge", response_model=LifeEventResponse)
def merge_event(
    event_id: int,
    body: MergeLifeEventRequest,
    db: Session = Depends(get_db),
) -> LifeEventResponse:
    source = db.get(LifeEvent, event_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source event not found")

    target = db.get(LifeEvent, body.into_event_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target event not found")

    if source.id == target.id:
        raise HTTPException(status_code=400, detail="Cannot merge an event into itself")

    for link in list(source.linked_assets):
        exists = any(existing.asset_id == link.asset_id for existing in target.linked_assets)
        if not exists:
            db.add(EventAsset(event_id=target.id, asset_id=link.asset_id, relation_type=link.relation_type))

    if not target.description and source.description:
        target.description = source.description
    if not target.event_date_text and source.event_date_text:
        target.event_date_text = source.event_date_text
        target.event_date_sort = source.event_date_sort
        target.date_precision = source.date_precision
        target.date_year = source.date_year
        target.date_month = source.date_month
        target.date_day = source.date_day
        target.date_decade = source.date_decade
    if target.period_id is None and source.period_id is not None:
        target.period_id = source.period_id
    if target.legacy_memory_id is None and source.legacy_memory_id is not None:
        target.legacy_memory_id = source.legacy_memory_id

    db.delete(source)
    db.commit()
    db.refresh(target)
    return build_event_response(target)


@app.delete("/api/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)) -> dict:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    db.delete(event)
    db.commit()
    return {"status": "deleted", "event_id": event_id}


@app.get("/api/events/{event_id}/assets", response_model=list[AssetResponse])
def list_event_assets(event_id: int, db: Session = Depends(get_db)) -> list[AssetResponse]:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    assets = [link.asset for link in event.linked_assets if link.asset]
    return [build_asset_response(asset) for asset in assets]


@app.get("/api/assets/unlinked", response_model=list[AssetResponse])
def list_unlinked_assets(db: Session = Depends(get_db)) -> list[AssetResponse]:
    assets = db.query(Asset).order_by(Asset.created_at.desc()).all()
    unlinked = [asset for asset in assets if not asset.event_links]
    return [build_asset_response(asset) for asset in unlinked]


@app.post("/api/assets", response_model=AssetResponse)
async def upload_asset(
    file: UploadFile = File(...),
    kind: str = Form("document"),
    period_id: Optional[int] = Form(None),
    event_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
) -> AssetResponse:
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Asset file is empty")

    if period_id is not None and not db.get(LifePeriod, period_id):
        raise HTTPException(status_code=404, detail="Period not found")

    event: Optional[LifeEvent] = None
    if event_id is not None:
        event = db.get(LifeEvent, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

    normalized_kind = (kind or "document").strip().lower()[:20]
    if normalized_kind == "audio" or (file.content_type or "").startswith("audio/"):
        storage_filename, content_type, size_bytes, stored_bytes = save_audio_file(file, file_bytes, AUDIO_STORAGE_DIR)
        original_filename = file.filename
        fingerprint = hashlib.sha256(stored_bytes).hexdigest()
        normalized_kind = "audio"
    else:
        (
            storage_filename,
            content_type,
            size_bytes,
            original_filename,
        ) = save_document_file(file, file_bytes, DOCUMENT_STORAGE_DIR)
        fingerprint = hashlib.sha256(file_bytes).hexdigest()

    asset = Asset(
        period_id=period_id,
        kind=normalized_kind,
        storage_filename=storage_filename,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        fingerprint_sha256=fingerprint,
        notes=notes,
    )
    db.add(asset)
    db.flush()

    if event:
        db.add(EventAsset(event_id=event.id, asset_id=asset.id, relation_type="evidence"))

    db.commit()
    db.refresh(asset)
    return build_asset_response(asset)


@app.post("/api/assets/{asset_id}/link-event/{event_id}", response_model=AssetResponse)
def link_asset_to_event(
    asset_id: int,
    event_id: int,
    body: LinkAssetToEventRequest,
    db: Session = Depends(get_db),
) -> AssetResponse:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    existing = (
        db.query(EventAsset)
        .filter(EventAsset.asset_id == asset_id, EventAsset.event_id == event_id)
        .first()
    )
    if not existing:
        db.add(EventAsset(event_id=event_id, asset_id=asset_id, relation_type=(body.relation_type or "evidence")[:30]))
        db.commit()
        db.refresh(asset)

    return build_asset_response(asset)


@app.get("/api/assets/{asset_id}/download")
def download_asset(asset_id: int, download: bool = True, db: Session = Depends(get_db)) -> FileResponse:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    storage_dir = AUDIO_STORAGE_DIR if asset.kind == "audio" else DOCUMENT_STORAGE_DIR
    file_path = storage_dir / asset.storage_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Asset file missing from storage")

    filename = asset.original_filename or asset.storage_filename
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path=file_path,
        media_type=(asset.content_type or "application/octet-stream"),
        filename=filename,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


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


@app.get("/api/memories/{memory_id}/document")
def get_memory_document(memory_id: int, download: bool = False, db: Session = Depends(get_db)) -> FileResponse:
    memory = db.get(MemoryEntry, memory_id)
    if not memory or not memory.document_filename:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = DOCUMENT_STORAGE_DIR / memory.document_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file missing from storage")

    filename = memory.document_original_filename or memory.document_filename
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path=file_path,
        media_type=(memory.document_content_type or "application/octet-stream"),
        filename=filename,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
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
    sync_life_hierarchy_for_memory(db, entry)
    db.commit()
    db.refresh(entry)

    if transcription_enabled and transcript not in ("Transcription failed.", "Transcription disabled."):
        try:
            add_unique_pending_questions(
                db,
                generate_questions_from_memory(transcript, event_description, metadata),
                entry.id,
            )
            db.commit()
        except Exception as exc:
            logger.warning("Could not generate questions for memory %s: %s", entry.id, exc)

    return entry


SUPPORTED_DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
    "text/plain",
}

_EXTENSION_TO_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".txt": "text/plain",
}


@app.post("/api/memories/document", response_model=MemoryResponse)
async def create_memory_from_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> MemoryEntry:
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Document file is empty")

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in SUPPORTED_DOCUMENT_MIME_TYPES:
        ext = Path(file.filename or "").suffix.lower()
        content_type = _EXTENSION_TO_MIME.get(ext, content_type)

    if content_type not in SUPPORTED_DOCUMENT_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{content_type}'. "
                "Supported: PDF, JPEG, PNG, GIF, WEBP, TXT"
            ),
        )

    transcript = extract_text_from_document(file.filename or "document", file_bytes, content_type)

    (
        document_filename,
        document_content_type,
        document_size_bytes,
        document_original_filename,
    ) = save_document_file(file, file_bytes, DOCUMENT_STORAGE_DIR)

    metadata = extract_metadata_with_gemini_function_call(transcript)
    if metadata is None:
        metadata = fallback_metadata_from_transcript(transcript)

    emotional_tone = "neutral"
    event_description = f"Document analysis: {document_original_filename}"
    follow_up_question = "What additional factual details should be captured from this document?"

    entry = MemoryEntry(
        transcript=transcript,
        event_description=event_description,
        estimated_date_text=metadata.date_text,
        estimated_date_sort=metadata.sort_date,
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
        audio_filename=None,
        audio_content_type=None,
        audio_size_bytes=None,
        document_filename=document_filename,
        document_original_filename=document_original_filename,
        document_content_type=document_content_type,
        document_size_bytes=document_size_bytes,
    )
    db.add(entry)
    db.flush()
    assign_recorder_person(db, entry, metadata.recorder_name)
    sync_memory_people(db, entry, metadata.people)
    sync_memory_places(db, entry, metadata.locations)
    sync_life_hierarchy_for_memory(db, entry)
    db.commit()
    db.refresh(entry)

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
    memory.research_summary = None
    memory.research_sources_json = None
    memory.research_queries_json = None
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
        add_unique_pending_questions(
            db,
            generate_questions_from_memory(transcript, event_description, metadata),
            memory.id,
        )

    db.commit()
    db.refresh(memory)
    return memory


def _extract_questions_from_research(summary: str) -> list[str]:
    """Extract bullet-point questions from the 'Questions worth exploring' section."""
    import re
    lines = summary.splitlines()
    in_section = False
    questions: list[str] = []
    section_headers = re.compile(r"^#{1,3}\s*questions worth exploring", re.IGNORECASE)
    next_section = re.compile(r"^#{1,3}\s+\w", re.IGNORECASE)
    bullet = re.compile(r"^[\*\-]\s+(.+)")

    for line in lines:
        stripped = line.strip()
        if section_headers.match(stripped):
            in_section = True
            continue
        if in_section:
            if next_section.match(stripped) and not section_headers.match(stripped):
                break
            m = bullet.match(stripped)
            if m:
                text = m.group(1).strip()
                if text.endswith("?"):
                    questions.append(text)
    return questions[:5]


@app.post("/api/memories/{memory_id}/research", response_model=MemoryResponse)
def research_memory(memory_id: int, db: Session = Depends(get_db)) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    # If memory has a document, read it to pass to research
    document_bytes = None
    document_mime_type = None
    if memory.document_filename:
        doc_path = DOCUMENT_STORAGE_DIR / memory.document_filename
        if doc_path.exists():
            with open(doc_path, "rb") as f:
                document_bytes = f.read()
            document_mime_type = memory.document_content_type or "application/octet-stream"

    research = research_memory_details(
        transcript=memory.transcript,
        event_description=memory.event_description,
        estimated_date_text=memory.estimated_date_text,
        referenced_locations=memory.referenced_locations,
        referenced_people=memory.referenced_people,
        document_bytes=document_bytes,
        document_mime_type=document_mime_type,
    )
    memory.research_summary = research.summary
    memory.research_queries_json = json.dumps(research.queries)
    memory.research_sources_json = json.dumps(
        [{"title": source.title, "url": source.url} for source in research.sources]
    )

    suggestion = suggest_date_from_research(
        research_summary=research.summary,
        current_date_text=memory.estimated_date_text,
        current_date_precision=memory.date_precision,
    )
    if suggestion:
        memory.research_suggested_metadata_json = json.dumps(dataclasses.asdict(suggestion))
    else:
        memory.research_suggested_metadata_json = None

    db.commit()
    db.refresh(memory)

    # Extract follow-up questions from the 'Questions worth exploring' section
    # already present in the research summary, rather than making a redundant Gemini call
    follow_up_questions = _extract_questions_from_research(research.summary)
    logger.info("Extracted %d questions from research summary", len(follow_up_questions))
    for question_text in follow_up_questions:
        logger.info("Adding question: %s", question_text[:80])
        db.add(Question(text=question_text, source_memory_id=memory_id, status="pending"))
    db.commit()

    return memory


@app.post("/api/memories/{memory_id}/apply-research-suggestion", response_model=MemoryResponse)
def apply_research_suggestion(memory_id: int, db: Session = Depends(get_db)) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    if not memory.research_suggested_metadata_json:
        raise HTTPException(status_code=404, detail="No pending suggestion")

    suggestion = json.loads(memory.research_suggested_metadata_json)
    memory.estimated_date_text = suggestion.get("estimated_date_text") or memory.estimated_date_text
    memory.date_precision = suggestion.get("date_precision") or memory.date_precision
    memory.date_year = suggestion.get("date_year")
    memory.date_month = suggestion.get("date_month")
    memory.date_day = suggestion.get("date_day")
    memory.date_decade = suggestion.get("date_decade")
    memory.estimated_date_sort = build_sort_date(
        memory.date_precision,
        memory.date_year,
        memory.date_month,
        memory.date_day,
        memory.date_decade,
    )
    memory.research_suggested_metadata_json = None
    db.commit()
    db.refresh(memory)
    return memory


@app.post("/api/memories/{memory_id}/dismiss-research-suggestion", response_model=MemoryResponse)
def dismiss_research_suggestion(memory_id: int, db: Session = Depends(get_db)) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory.research_suggested_metadata_json = None
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
    document_path = DOCUMENT_STORAGE_DIR / memory.document_filename if memory.document_filename else None
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

    if document_path and document_path.exists():
        try:
            document_path.unlink()
        except OSError:
            logger.warning("Could not delete document file for memory %s", memory_id)

    return {"status": "deleted", "memory_id": memory_id}


@app.get("/api/questions", response_model=list[QuestionResponse])
def list_questions(db: Session = Depends(get_db)) -> list[Question]:
    pending = (
        db.query(Question)
        .filter(Question.status == "pending")
        .order_by(Question.created_at.asc())
        .all()
    )

    deduped: list[Question] = []
    seen: set[str] = set()
    for question in pending:
        normalized = normalize_question_text(question.text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(question)

    return deduped


@app.post("/api/questions/{question_id}/answer")
def answer_question(
    question_id: int,
    body: AnswerQuestionRequest,
    db: Session = Depends(get_db),
) -> dict:
    question = db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    memory: Optional[MemoryEntry] = None
    if body.answer_memory_id is not None:
        memory = db.get(MemoryEntry, body.answer_memory_id)
        if not memory:
            raise HTTPException(status_code=404, detail="Answer memory not found")

    question.status = "answered"
    question.answer_memory_id = body.answer_memory_id
    if memory:
        memory.response_to_question_id = question.id
        memory.response_to_question_text = question.text
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


_ALLOWED_SETTING_KEYS = {"main_character_name"}


@app.get("/api/settings", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)) -> SettingsResponse:
    rows = db.query(Setting).all()
    mapping = {row.key: row.value for row in rows}
    return SettingsResponse(main_character_name=mapping.get("main_character_name"))


@app.put("/api/settings/{key}")
def update_setting(
    key: str,
    body: UpdateSettingRequest,
    db: Session = Depends(get_db),
) -> dict:
    if key not in _ALLOWED_SETTING_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown setting key: {key}")
    setting = db.get(Setting, key)
    if setting:
        setting.value = body.value
        setting.updated_at = datetime.utcnow()
    else:
        db.add(Setting(key=key, value=body.value))
    db.commit()
    return {"key": key, "value": body.value}
