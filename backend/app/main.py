import dataclasses
import hashlib
import json
import logging
import os
import re
from collections import Counter
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
    AnalyzeLifePeriodRequest,
    AssetResponse,
    AddAliasRequest,
    AnswerQuestionRequest,
    CreateLifeEventRequest,
    CreateLifePeriodRequest,
    CreateDirectoryEntryRequest,
    DirectoryEntryResponse,
    LifeEventResponse,
    LifePeriodAnalysisResponse,
    LifePeriodResponse,
    MergeLifeEventRequest,
    LinkAssetToEventRequest,
    MemoryResponse,
    MergePersonRequest,
    QuestionResponse,
    UpdateAssetRequest,
    UpdateLifeEventRequest,
    UpdateLifePeriodRequest,
    MergePeriodsRequest,
    SettingsResponse,
    SplitPersonRequest,
    UpdateDirectoryEntryRequest,
    UpdateMemoryRequest,
    UpdateMemoryRecorderRequest,
    UpdateSettingRequest,
)
from app.services.audio_storage import save_audio_file
from app.services.document_storage import save_document_file
from app.services.gemini_client import (
    extract_metadata_with_gemini_function_call,
    research_memory_details,
    suggest_event_edit_from_context,
    summarize_event_details,
    suggest_date_from_research,
)
from app.services.gemini_client import extract_text_from_document
from app.services.image_metadata import extract_and_apply_image_metadata
from app.services.directory import (
    assign_recorder_person,
    build_directory_response,
    get_or_create_person,
    get_or_create_place,
    list_people_directory,
    list_places_directory,
    sync_memory_people,
    sync_memory_places,
    update_memory_json_from_links,
)
from app.services.life_hierarchy import (
    backfill_life_hierarchy,
    backfill_normalized_directory,
    sync_life_hierarchy_for_memory,
)
from app.services.memory_ingest import analyze_memory_audio
from app.services.periods import (
    analyze_period,
    build_asset_response,
    build_event_response,
    build_period_response,
    ensure_event_asset_link,
    normalize_directory_name,
    normalize_period_title,
    refresh_period_summary,
    unique_period_slug,
)
from app.services.questions import (
    add_unique_pending_questions,
    normalize_question_text,
    seed_initial_questions,
)
from app.services.memory_analysis import (
    build_sort_date,
    fallback_metadata_from_transcript,
    generate_questions_from_memory,
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
    logger.info("Registered models: %s", [table for table in Base.metadata.tables.keys()])
    logger.info("Creating tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tables after create_all: %s", [table for table in Base.metadata.tables.keys()])
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


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {"service": "memoir-api", "health": "/api/health"}


def derive_asset_title(filename: Optional[str]) -> Optional[str]:
    candidate = (filename or "").strip()
    if not candidate:
        return None
    stem = Path(candidate).stem.strip() or candidate
    return stem[:180]


@app.get("/api/periods", response_model=list[LifePeriodResponse])
def list_periods(db: Session = Depends(get_db)) -> list[LifePeriodResponse]:
    periods = db.query(LifePeriod).order_by(LifePeriod.start_sort.asc().nulls_last(), LifePeriod.created_at.asc()).all()
    return [build_period_response(period) for period in periods]


@app.patch("/api/periods/{period_id}", response_model=LifePeriodResponse)
def update_period(period_id: int, body: UpdateLifePeriodRequest, db: Session = Depends(get_db)) -> LifePeriodResponse:
    period = db.get(LifePeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    if body.title is not None:
        clean_title = normalize_period_title(body.title)
        if not clean_title:
            raise HTTPException(status_code=400, detail="Period title cannot be empty")
        period.title = clean_title
        period.slug = unique_period_slug(db, clean_title, existing_id=period.id)

    if body.start_date_text is not None:
        period.start_date_text = body.start_date_text.strip() or None

    if body.end_date_text is not None:
        period.end_date_text = body.end_date_text.strip() or None

    db.commit()
    db.refresh(period)
    return build_period_response(period)


@app.delete("/api/periods/{period_id}", status_code=204)
def delete_period(period_id: int, db: Session = Depends(get_db)) -> None:
    period = db.get(LifePeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    # Detach events and assets from the period before deleting
    db.query(LifeEvent).filter(LifeEvent.period_id == period_id).update({"period_id": None})
    db.query(Asset).filter(Asset.period_id == period_id).update({"period_id": None})
    db.delete(period)
    db.commit()


@app.post("/api/periods/{period_id}/merge", status_code=204)
def merge_period(period_id: int, body: MergePeriodsRequest, db: Session = Depends(get_db)) -> None:
    source = db.get(LifePeriod, period_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source period not found")
    target = db.get(LifePeriod, body.into_period_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target period not found")
    if source.id == target.id:
        raise HTTPException(status_code=400, detail="Cannot merge a period into itself")

    # Move events and assets from source → target
    db.query(LifeEvent).filter(LifeEvent.period_id == source.id).update({"period_id": target.id})
    db.query(Asset).filter(Asset.period_id == source.id).update({"period_id": target.id})
    db.delete(source)
    db.commit()
    # Refresh the target summary now that it has more content
    db.refresh(target)
    refresh_period_summary(db, target, force=False)
    db.commit()


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


@app.post("/api/periods/{period_id}/analyze", response_model=LifePeriodAnalysisResponse)
def analyze_life_period(
    period_id: int,
    body: AnalyzeLifePeriodRequest = Body(default=AnalyzeLifePeriodRequest()),
    db: Session = Depends(get_db),
) -> LifePeriodAnalysisResponse:
    period = db.get(LifePeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    events = (
        db.query(LifeEvent)
        .filter(LifeEvent.period_id == period.id)
        .order_by(LifeEvent.event_date_sort.is_(None), LifeEvent.event_date_sort.asc(), LifeEvent.created_at.asc())
        .all()
    )

    analysis = analyze_period(period, events, len(period.assets))

    if body.apply_dates and analysis.recommended_start_date_text and analysis.recommended_end_date_text:
        try:
            start_year = int(analysis.recommended_start_date_text)
            end_year = int(analysis.recommended_end_date_text)
            period.start_date_text = analysis.recommended_start_date_text
            period.end_date_text = analysis.recommended_end_date_text
            period.start_sort = date(start_year, 1, 1)
            period.end_sort = date(end_year, 12, 31)
        except ValueError:
            # Keep textual recommendations without applying sort dates.
            period.start_date_text = analysis.recommended_start_date_text
            period.end_date_text = analysis.recommended_end_date_text

    if body.apply_title and analysis.recommended_titles:
        period.title = analysis.recommended_titles[0]
        period.slug = unique_period_slug(db, analysis.recommended_titles[0], existing_id=period.id)

    if body.apply_title_text:
        clean = body.apply_title_text.strip()[:160]
        if clean:
            period.title = clean
            period.slug = unique_period_slug(db, clean, existing_id=period.id)

    if body.regenerate_summary:
        refresh_period_summary(db, period, force=True)

    if body.apply_dates or body.apply_title or body.regenerate_summary:
        db.commit()
        db.refresh(period)
        events = (
            db.query(LifeEvent)
            .filter(LifeEvent.period_id == period.id)
            .order_by(LifeEvent.event_date_sort.is_(None), LifeEvent.event_date_sort.asc(), LifeEvent.created_at.asc())
            .all()
        )

    return analyze_period(period, events, len(period.assets))


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
    if body.period_id is not None:
        period = db.get(LifePeriod, body.period_id)
        refresh_period_summary(db, period)
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


@app.patch("/api/events/{event_id}", response_model=LifeEventResponse)
def update_event(event_id: int, body: UpdateLifeEventRequest, db: Session = Depends(get_db)) -> LifeEventResponse:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if body.title is not None:
        clean_title = body.title.strip()
        if not clean_title:
            raise HTTPException(status_code=400, detail="Event title cannot be empty")
        event.title = clean_title

    if "description" in body.model_fields_set:
        event.description = (body.description or "").strip()[:1200] or None

    if "event_date_text" in body.model_fields_set:
        next_date_text = (body.event_date_text or "").strip()[:100]
        event.event_date_text = next_date_text or None

    db.commit()
    db.refresh(event)
    return build_event_response(event)


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

    target_period = db.get(LifePeriod, target.period_id) if target.period_id else None
    source_period = db.get(LifePeriod, source.period_id) if source.period_id else None
    refresh_period_summary(db, target_period)
    if source_period and (not target_period or source_period.id != target_period.id):
        refresh_period_summary(db, source_period)

    db.delete(source)
    db.commit()
    db.refresh(target)
    return build_event_response(target)


@app.delete("/api/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)) -> dict:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    period = db.get(LifePeriod, event.period_id) if event.period_id else None
    db.delete(event)
    refresh_period_summary(db, period)
    db.commit()
    return {"status": "deleted", "event_id": event_id}


@app.get("/api/events/{event_id}/assets", response_model=list[AssetResponse])
def list_event_assets(event_id: int, db: Session = Depends(get_db)) -> list[AssetResponse]:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    assets = [link.asset for link in event.linked_assets if link.asset]
    return [build_asset_response(asset) for asset in assets]


@app.post("/api/events/{event_id}/summarize", response_model=LifeEventResponse)
def summarize_event(event_id: int, db: Session = Depends(get_db)) -> LifeEventResponse:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    memories = _collect_event_memories(event, db)
    assets = [link.asset for link in event.linked_assets if link.asset]

    memory_points: list[str] = []
    for memory in memories:
        heading = (memory.event_description or "").strip() or f"Memory {memory.id}"
        transcript = " ".join((memory.transcript or "").split())
        if transcript:
            memory_points.append(f"{heading}: {transcript[:280]}")
        else:
            memory_points.append(heading)

    asset_points: list[str] = []
    for asset in assets:
        title = (asset.title or asset.original_filename or f"Asset {asset.id}").strip()
        details = []
        if asset.notes:
            details.append(" ".join(asset.notes.split())[:180])
        if asset.text_excerpt:
            details.append(" ".join(asset.text_excerpt.split())[:180])
        if asset.captured_at_text:
            details.append(asset.captured_at_text)
        if details:
            asset_points.append(f"{title}: {' | '.join(details)}")
        else:
            asset_points.append(title)

    summary = summarize_event_details(
        event_title=event.title,
        event_date_text=event.event_date_text,
        memory_points=memory_points,
        asset_points=asset_points,
    )
    event.summary = summary
    suggestion = suggest_event_edit_from_context(
        analysis_text=summary,
        current_title=event.title,
        current_event_date_text=event.event_date_text,
        current_description=event.description,
    )
    event.research_suggested_edit_json = json.dumps(dataclasses.asdict(suggestion)) if suggestion else None

    db.commit()
    db.refresh(event)
    return build_event_response(event)


@app.post("/api/events/{event_id}/research", response_model=LifeEventResponse)
def research_event(event_id: int, db: Session = Depends(get_db)) -> LifeEventResponse:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    memories = _collect_event_memories(event, db)
    assets = [link.asset for link in event.linked_assets if link.asset]

    transcript_sections: list[str] = [f"Event title: {event.title}"]
    if event.description:
        transcript_sections.append(f"Event description: {event.description}")

    for memory in memories:
        transcript_sections.append(f"Memory: {memory.event_description}")
        transcript_sections.append(memory.transcript or "")

    for asset in assets:
        asset_title = asset.title or asset.original_filename or f"Asset {asset.id}"
        transcript_sections.append(f"Asset: {asset_title}")
        if asset.notes:
            transcript_sections.append(f"Notes: {asset.notes}")
        if asset.text_excerpt:
            transcript_sections.append(f"Extracted text: {asset.text_excerpt}")
        if asset.captured_at_text:
            transcript_sections.append(f"Captured at: {asset.captured_at_text}")

    combined_transcript = "\n\n".join(section for section in transcript_sections if section.strip())[:20000]
    people = sorted({name for memory in memories for name in memory.referenced_people if name})
    locations = sorted({name for memory in memories for name in memory.referenced_locations if name})

    research = research_memory_details(
        transcript=combined_transcript,
        event_description=event.title,
        estimated_date_text=event.event_date_text,
        referenced_locations=locations,
        referenced_people=people,
        document_bytes=None,
        document_mime_type=None,
    )

    event.research_summary = research.summary
    event.research_queries_json = json.dumps(research.queries)
    event.research_sources_json = json.dumps(
        [{"title": source.title, "url": source.url} for source in research.sources]
    )
    suggestion = suggest_event_edit_from_context(
        analysis_text=research.summary,
        current_title=event.title,
        current_event_date_text=event.event_date_text,
        current_description=event.description,
    )
    event.research_suggested_edit_json = json.dumps(dataclasses.asdict(suggestion)) if suggestion else None

    source_memory_id = _event_research_source_memory_id(event, memories)
    if source_memory_id is not None:
        add_unique_pending_questions(
            db,
            _extract_questions_from_research(research.summary),
            source_memory_id,
        )

    db.commit()
    db.refresh(event)
    return build_event_response(event)


@app.post("/api/events/{event_id}/apply-research-suggestion", response_model=LifeEventResponse)
def apply_event_research_suggestion(event_id: int, db: Session = Depends(get_db)) -> LifeEventResponse:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not event.research_suggested_edit_json:
        raise HTTPException(status_code=404, detail="No pending suggestion")

    suggestion = json.loads(event.research_suggested_edit_json)
    if isinstance(suggestion, dict):
        next_title = (suggestion.get("title") or "").strip()
        next_date_text = (suggestion.get("event_date_text") or "").strip()
        next_description = (suggestion.get("description") or "").strip()

        if next_title:
            event.title = next_title[:180]
        if next_date_text:
            event.event_date_text = next_date_text[:100]
        if next_description:
            event.description = next_description[:1200]

    event.research_suggested_edit_json = None
    db.commit()
    db.refresh(event)
    return build_event_response(event)


@app.post("/api/events/{event_id}/dismiss-research-suggestion", response_model=LifeEventResponse)
def dismiss_event_research_suggestion(event_id: int, db: Session = Depends(get_db)) -> LifeEventResponse:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.research_suggested_edit_json = None
    db.commit()
    db.refresh(event)
    return build_event_response(event)


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
        title=derive_asset_title(original_filename),
        storage_filename=storage_filename,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        fingerprint_sha256=fingerprint,
        notes=notes,
    )
    if normalized_kind != "audio":
        extract_and_apply_image_metadata(asset, file_bytes, content_type)

    db.add(asset)
    db.flush()

    if event:
        db.add(EventAsset(event_id=event.id, asset_id=asset.id, relation_type="evidence"))

    period_for_summary: Optional[LifePeriod] = None
    if period_id is not None:
        period_for_summary = db.get(LifePeriod, period_id)
    elif event and event.period_id is not None:
        period_for_summary = db.get(LifePeriod, event.period_id)

    refresh_period_summary(db, period_for_summary)

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
        period = db.get(LifePeriod, event.period_id) if event.period_id else None
        refresh_period_summary(db, period)
        db.commit()
        db.refresh(asset)

    return build_asset_response(asset)


@app.patch("/api/assets/{asset_id}", response_model=AssetResponse)
def update_asset(asset_id: int, body: UpdateAssetRequest, db: Session = Depends(get_db)) -> AssetResponse:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if "title" in body.model_fields_set:
        clean_title = body.title.strip() if body.title is not None else None
        asset.title = (clean_title or None)

    if "notes" in body.model_fields_set:
        clean_notes = body.notes.strip() if body.notes is not None else None
        asset.notes = clean_notes or None

    db.commit()
    db.refresh(asset)
    return build_asset_response(asset)


@app.delete("/api/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db)) -> None:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    storage_dir = AUDIO_STORAGE_DIR if asset.kind == "audio" else DOCUMENT_STORAGE_DIR
    file_path = storage_dir / asset.storage_filename if asset.storage_filename else None

    db.delete(asset)
    db.commit()

    if file_path and file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            logger.warning("Could not delete file for asset %s", asset_id)


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
    event_id: Optional[int] = Form(None),
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

    if event_id is not None:
        # Narration is being recorded directly for a specific event.
        # Skip sync_life_hierarchy_for_memory (which would create an unwanted
        # second event) and instead create the audio asset + link it manually.
        target_event = db.query(LifeEvent).filter(LifeEvent.id == event_id).first()
        if target_event:
            conflicting_asset = db.query(Asset).filter(Asset.legacy_memory_id == entry.id).first()
            if conflicting_asset and conflicting_asset.kind != "audio":
                conflicting_asset.legacy_memory_id = None
                db.flush()

            audio_asset = (
                db.query(Asset)
                .filter(Asset.legacy_memory_id == entry.id, Asset.kind == "audio")
                .first()
            )
            if not audio_asset:
                audio_asset = Asset(
                    period_id=target_event.period_id,
                    kind="audio",
                    title=derive_asset_title(audio_filename),
                    storage_filename=audio_filename,
                    original_filename=audio_filename,
                    content_type=audio_content_type,
                    size_bytes=audio_size_bytes,
                    text_excerpt=(transcript or "").strip()[:1200] or None,
                    notes=f"Audio narration for event: {target_event.title}",
                    legacy_memory_id=entry.id,
                )
                db.add(audio_asset)
                db.flush()
            ensure_event_asset_link(db, target_event, audio_asset, relation_type="recording")
    else:
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
    event_id: Optional[int] = Form(None),
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

    if event_id is not None:
        target_event = db.query(LifeEvent).filter(LifeEvent.id == event_id).first()
        if target_event:
            asset_kind = "photo" if (document_content_type or "").startswith("image/") else "document"
            conflicting_asset = db.query(Asset).filter(Asset.legacy_memory_id == entry.id).first()
            if conflicting_asset and conflicting_asset.kind != asset_kind:
                conflicting_asset.legacy_memory_id = None
                db.flush()

            document_asset = Asset(
                period_id=target_event.period_id,
                kind=asset_kind,
                title=derive_asset_title(document_original_filename or ""),
                storage_filename=document_filename,
                original_filename=document_original_filename,
                content_type=document_content_type,
                size_bytes=document_size_bytes,
                text_excerpt=(transcript or "").strip()[:1200] or None,
                notes=f"Uploaded to event: {target_event.title}",
                legacy_memory_id=entry.id,
            )
            db.add(document_asset)
            db.flush()
            if asset_kind == "photo" and document_filename:
                doc_path = DOCUMENT_STORAGE_DIR / document_filename
                if doc_path.exists():
                    try:
                        extract_and_apply_image_metadata(document_asset, doc_path.read_bytes(), document_content_type)
                    except Exception:
                        pass
            ensure_event_asset_link(db, target_event, document_asset)
            if target_event.legacy_memory_id is None:
                target_event.legacy_memory_id = entry.id
    else:
        sync_life_hierarchy_for_memory(db, entry)

    db.commit()
    db.refresh(entry)

    return entry


@app.post("/api/memories/{memory_id}/reanalyze", response_model=MemoryResponse)
def reanalyze_memory(memory_id: int, db: Session = Depends(get_db)) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    # --- Document memory reanalysis ---
    if memory.document_filename and not memory.audio_filename:
        file_path = DOCUMENT_STORAGE_DIR / memory.document_filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Document file missing from storage")

        file_bytes = file_path.read_bytes()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Stored document is empty")

        content_type = memory.document_content_type or "application/octet-stream"
        transcript = extract_text_from_document(
            memory.document_original_filename or memory.document_filename,
            file_bytes,
            content_type,
        )

        metadata = extract_metadata_with_gemini_function_call(transcript)
        if metadata is None:
            metadata = fallback_metadata_from_transcript(transcript)

        memory.transcript = transcript
        memory.estimated_date_sort = metadata.sort_date
        memory.estimated_date_text = metadata.date_text
        memory.date_precision = metadata.date_precision
        memory.date_year = metadata.date_year
        memory.date_month = metadata.date_month
        memory.date_day = metadata.date_day
        memory.date_decade = metadata.date_decade
        memory.people_json = json.dumps(metadata.people)
        memory.locations_json = json.dumps(metadata.locations)
        memory.research_summary = None
        memory.research_sources_json = None
        memory.research_queries_json = None
        if not memory.recorder_person_id and not memory.recorder_name:
            assign_recorder_person(db, memory, metadata.recorder_name)
        sync_memory_people(db, memory, metadata.people)
        sync_memory_places(db, memory, metadata.locations)
        sync_life_hierarchy_for_memory(db, memory)

        db.commit()
        db.refresh(memory)
        return memory

    # --- Audio memory reanalysis ---
    if not memory.audio_filename:
        raise HTTPException(status_code=400, detail="Memory has no stored audio or document to reanalyze")

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


def _collect_event_memories(event: LifeEvent, db: Session) -> list[MemoryEntry]:
    memory_ids: list[int] = []
    if event.legacy_memory_id is not None:
        memory_ids.append(event.legacy_memory_id)

    for link in event.linked_assets:
        asset = link.asset
        if asset and asset.legacy_memory_id is not None:
            memory_ids.append(asset.legacy_memory_id)

    seen: set[int] = set()
    memories: list[MemoryEntry] = []
    for memory_id in memory_ids:
        if memory_id in seen:
            continue
        seen.add(memory_id)
        memory = db.get(MemoryEntry, memory_id)
        if memory:
            memories.append(memory)
    return memories


def _event_research_source_memory_id(event: LifeEvent, memories: list[MemoryEntry]) -> Optional[int]:
    if event.legacy_memory_id is not None:
        return event.legacy_memory_id
    if memories:
        return memories[0].id
    return None


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


@app.patch("/api/memories/{memory_id}", response_model=MemoryResponse)
def update_memory(memory_id: int, body: UpdateMemoryRequest, db: Session = Depends(get_db)) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    if "event_description" in body.model_fields_set:
        next_value = (body.event_description or "").strip()
        if not next_value:
            raise HTTPException(status_code=400, detail="Memory title cannot be empty")
        memory.event_description = next_value[:240]

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
