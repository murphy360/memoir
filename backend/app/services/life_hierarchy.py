from sqlalchemy.orm import Session

from app.models import Asset, LifeEvent, MemoryEntry
from app.services.directory import assign_recorder_person, sync_memory_people, sync_memory_places
from app.services.periods import ensure_event_asset_link, get_or_create_period_for_memory


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
    elif event.period_id is None:
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
        elif document_asset.period_id is None:
            document_asset.period_id = period.id

        ensure_event_asset_link(db, event, document_asset)


def backfill_normalized_directory(db: Session) -> None:
    for memory in db.query(MemoryEntry).all():
        recorder_name = memory.recorder_name
        if not recorder_name and memory.recorder_person:
            recorder_name = memory.recorder_person.name
        assign_recorder_person(db, memory, recorder_name)
        sync_memory_people(db, memory, memory.referenced_people)
        sync_memory_places(db, memory, memory.referenced_locations)

    db.commit()


def backfill_life_hierarchy(db: Session) -> None:
    memories = db.query(MemoryEntry).order_by(MemoryEntry.created_at.asc()).all()

    for memory in memories:
        sync_life_hierarchy_for_memory(db, memory)

    db.commit()
