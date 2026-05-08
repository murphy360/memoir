"""Queue and batch-process uploaded photo assets.

This service keeps a lightweight in-memory queue for photo uploads so callers can
stage many photos first, then process them in one Gemini request.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Asset, EventAsset, LifeEvent, LifePeriod
from app.services.document_storage import save_document_file
from app.services.faces import FACE_DETECTION_ON_INGEST, sync_asset_faces_for_photo
from app.services.gemini_client import PhotoSummary, extract_text_from_photo_batch
from app.services.image_metadata import extract_and_apply_image_metadata, extract_image_metadata
from app.services.periods import refresh_period_summary


@dataclass
class QueuedPhotoUpload:
    filename: str
    content_type: str
    file_bytes: bytes
    period_id: Optional[int]
    event_id: Optional[int]
    notes: Optional[str]


class _UploadLike:
    def __init__(self, filename: str, content_type: str) -> None:
        self.filename = filename
        self.content_type = content_type


_photo_queue: list[QueuedPhotoUpload] = []
_photo_queue_lock = Lock()


def _derive_asset_title(filename: str) -> Optional[str]:
    candidate = (filename or "").strip()
    if not candidate:
        return None
    stem = Path(candidate).stem.strip() or candidate
    return stem[:180]


def _build_photo_metadata_hint(
    *,
    captured_at_text: Optional[str],
    captured_at: Optional[object],
    gps_latitude: Optional[float],
    gps_longitude: Optional[float],
    exif_place_name: Optional[str],
    reverse_geocode_location_name: Optional[str],
    camera_make: Optional[str],
    camera_model: Optional[str],
) -> str:
    parts: list[str] = []
    if captured_at_text:
        parts.append(f"captured_at={captured_at_text}")
    elif captured_at is not None:
        parts.append(f"captured_at={captured_at}")
    if gps_latitude is not None and gps_longitude is not None:
        parts.append(f"gps={gps_latitude:.6f},{gps_longitude:.6f}")
    if exif_place_name:
        parts.append(f"exif_place_name={exif_place_name}")
    if reverse_geocode_location_name:
        parts.append(f"reverse_geocode_location_name={reverse_geocode_location_name}")
    if camera_make or camera_model:
        camera_label = " ".join(part for part in [camera_make, camera_model] if part)
        parts.append(f"camera={camera_label}")
    return "; ".join(parts)


def enqueue_photo_uploads(items: list[QueuedPhotoUpload]) -> int:
    """Enqueue photo uploads and return the new queue size."""
    if not items:
        return get_photo_queue_size()
    with _photo_queue_lock:
        _photo_queue.extend(items)
        return len(_photo_queue)


def get_photo_queue_size() -> int:
    """Return current number of queued photo uploads."""
    with _photo_queue_lock:
        return len(_photo_queue)


def _drain_photo_queue(max_items: Optional[int] = None) -> list[QueuedPhotoUpload]:
    with _photo_queue_lock:
        if not _photo_queue:
            return []
        if max_items is None or max_items <= 0 or max_items >= len(_photo_queue):
            drained = list(_photo_queue)
            _photo_queue.clear()
            return drained
        drained = _photo_queue[:max_items]
        del _photo_queue[:max_items]
        return drained


def process_queued_photo_uploads(
    db: Session,
    document_storage_dir: Path,
    *,
    max_items: Optional[int] = None,
) -> list[Asset]:
    """Persist queued photos and analyze them in a single Gemini batch request."""
    queued = _drain_photo_queue(max_items=max_items)
    if not queued:
        return []

    payloads: list[tuple[str, bytes, str, str | None]] = []
    for item in queued:
        metadata = extract_image_metadata(item.file_bytes, item.content_type)
        metadata_hint = _build_photo_metadata_hint(
            captured_at_text=metadata.captured_at_text,
            captured_at=metadata.captured_at,
            gps_latitude=metadata.gps_latitude,
            gps_longitude=metadata.gps_longitude,
            exif_place_name=metadata.exif_place_name,
            reverse_geocode_location_name=metadata.reverse_geocode_location_name,
            camera_make=metadata.camera_make,
            camera_model=metadata.camera_model,
        )
        payloads.append((item.filename, item.file_bytes, item.content_type, metadata_hint or None))
    batch_summaries = extract_text_from_photo_batch(payloads)

    assets: list[Asset] = []
    periods_to_refresh: set[int] = set()

    for index, item in enumerate(queued, start=1):
        upload_like = _UploadLike(item.filename, item.content_type)
        (
            storage_filename,
            content_type,
            size_bytes,
            original_filename,
        ) = save_document_file(upload_like, item.file_bytes, document_storage_dir)

        asset = Asset(
            period_id=item.period_id,
            kind="photo",
            title=_derive_asset_title(original_filename),
            storage_filename=storage_filename,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            fingerprint_sha256=hashlib.sha256(item.file_bytes).hexdigest(),
            notes=item.notes,
            text_excerpt=batch_summaries.get(index, PhotoSummary("")).summary or None,
        )
        # Prefer Gemini's suggested title over the filename-derived one when available
        photo_result = batch_summaries.get(index)
        if photo_result and photo_result.suggested_title:
            asset.gemini_suggested_title = photo_result.suggested_title
            asset.title = photo_result.suggested_title
        if photo_result and photo_result.assessed_place:
            asset.analyzed_place_name = photo_result.assessed_place
        extract_and_apply_image_metadata(asset, item.file_bytes, content_type)

        db.add(asset)
        db.flush()
        if FACE_DETECTION_ON_INGEST:
            sync_asset_faces_for_photo(db, asset, item.file_bytes)

        event: Optional[LifeEvent] = None
        if item.event_id is not None:
            event = db.get(LifeEvent, item.event_id)
            if event is not None:
                db.add(EventAsset(event_id=event.id, asset_id=asset.id, relation_type="evidence"))

        period_for_summary: Optional[LifePeriod] = None
        if item.period_id is not None:
            period_for_summary = db.get(LifePeriod, item.period_id)
        elif event is not None and event.period_id is not None:
            period_for_summary = db.get(LifePeriod, event.period_id)

        if period_for_summary is not None:
            periods_to_refresh.add(period_for_summary.id)

        assets.append(asset)

    for period_id in periods_to_refresh:
        period = db.get(LifePeriod, period_id)
        refresh_period_summary(db, period)

    return assets


def _has_text_excerpt(asset: Asset) -> bool:
    return bool((asset.text_excerpt or "").strip())


def process_single_photo_asset(
    db: Session,
    document_storage_dir: Path,
    *,
    asset: Asset,
    include_processed: bool = True,
    force_faces: bool = False,
) -> tuple[bool, Optional[str]]:
    """Process one stored photo asset and refresh linked period summaries.

    Returns (True, suggested_title) when processing ran and the asset was updated.
    Returns (False, None) when the asset is not eligible (non-photo, missing file,
    or already processed when include_processed is False).
    """
    if asset.kind != "photo":
        return False, None
    if not include_processed and _has_text_excerpt(asset):
        return False, None
    if not asset.storage_filename:
        return False, None

    file_path = document_storage_dir / asset.storage_filename
    if not file_path.exists():
        return False, None

    try:
        file_bytes = file_path.read_bytes()
    except OSError:
        return False, None

    if not file_bytes:
        return False, None

    mime_type = (asset.content_type or "image/jpeg").strip().lower() or "image/jpeg"
    extract_and_apply_image_metadata(asset, file_bytes, mime_type)
    metadata_hint = _build_photo_metadata_hint(
        captured_at_text=asset.captured_at_text,
        captured_at=asset.captured_at,
        gps_latitude=asset.gps_latitude,
        gps_longitude=asset.gps_longitude,
        exif_place_name=asset.exif_place_name,
        reverse_geocode_location_name=asset.reverse_geocode_location_name,
        camera_make=asset.camera_make,
        camera_model=asset.camera_model,
    )
    summaries = extract_text_from_photo_batch([
        (asset.original_filename or asset.storage_filename, file_bytes, mime_type, metadata_hint or None),
    ])

    if force_faces or FACE_DETECTION_ON_INGEST:
        sync_asset_faces_for_photo(db, asset, file_bytes)
    photo_result = summaries.get(1)
    suggested_title: Optional[str] = None
    if photo_result:
        asset.text_excerpt = photo_result.summary
        suggested_title = photo_result.suggested_title
        asset.gemini_suggested_title = photo_result.suggested_title
        if photo_result.suggested_title:
            asset.title = photo_result.suggested_title
        asset.analyzed_place_name = photo_result.assessed_place

    period_ids_to_refresh: set[int] = set()
    if asset.period_id is not None:
        period_ids_to_refresh.add(asset.period_id)
    for event_link in asset.event_links:
        event = event_link.event
        if event and event.period_id is not None:
            period_ids_to_refresh.add(event.period_id)

    for period_id in period_ids_to_refresh:
        period = db.get(LifePeriod, period_id)
        refresh_period_summary(db, period)

    return True, suggested_title


def process_event_photo_assets(
    db: Session,
    document_storage_dir: Path,
    *,
    event: LifeEvent,
    include_processed: bool = False,
    max_items: Optional[int] = None,
) -> list[Asset]:
    """Batch-process existing photo assets linked to one event."""
    event_links = sorted(event.linked_assets, key=lambda link: link.created_at)
    candidates: list[Asset] = []
    for link in event_links:
        asset = link.asset
        if not asset or asset.kind != "photo":
            continue
        if not include_processed and _has_text_excerpt(asset):
            continue
        if not asset.storage_filename:
            continue
        candidates.append(asset)

    if max_items is not None and max_items > 0:
        candidates = candidates[:max_items]

    if not candidates:
        return []

    payloads: list[tuple[str, bytes, str, str | None]] = []
    valid_assets: list[Asset] = []
    for asset in candidates:
        file_path = document_storage_dir / asset.storage_filename
        if not file_path.exists():
            continue
        try:
            file_bytes = file_path.read_bytes()
        except OSError:
            continue
        if not file_bytes:
            continue
        mime_type = (asset.content_type or "image/jpeg").strip().lower() or "image/jpeg"
        extract_and_apply_image_metadata(asset, file_bytes, mime_type)
        metadata_hint = _build_photo_metadata_hint(
            captured_at_text=asset.captured_at_text,
            captured_at=asset.captured_at,
            gps_latitude=asset.gps_latitude,
            gps_longitude=asset.gps_longitude,
            exif_place_name=asset.exif_place_name,
            reverse_geocode_location_name=asset.reverse_geocode_location_name,
            camera_make=asset.camera_make,
            camera_model=asset.camera_model,
        )
        payloads.append((asset.original_filename or asset.storage_filename, file_bytes, mime_type, metadata_hint or None))
        valid_assets.append(asset)

    if not payloads:
        return []

    summaries = extract_text_from_photo_batch(payloads)
    updated_assets: list[Asset] = []
    for index, asset in enumerate(valid_assets, start=1):
        if FACE_DETECTION_ON_INGEST:
            sync_asset_faces_for_photo(db, asset, payloads[index - 1][1])
        photo_result = summaries.get(index)
        if not photo_result:
            continue
        asset.text_excerpt = photo_result.summary
        if photo_result.suggested_title:
            asset.gemini_suggested_title = photo_result.suggested_title
            asset.title = photo_result.suggested_title
        asset.analyzed_place_name = photo_result.assessed_place
        updated_assets.append(asset)

    if updated_assets and event.period_id is not None:
        period = db.get(LifePeriod, event.period_id)
        refresh_period_summary(db, period)

    return updated_assets


def process_events_photo_assets(
    db: Session,
    document_storage_dir: Path,
    *,
    event_id: Optional[int] = None,
    include_processed: bool = False,
    max_events: Optional[int] = None,
    max_items_per_event: Optional[int] = None,
) -> dict:
    """Process photo assets event-by-event using one Gemini batch call per event."""
    if event_id is not None:
        event = db.get(LifeEvent, event_id)
        if event is None:
            return {
                "events_processed": 0,
                "photos_processed": 0,
                "processed_asset_ids": [],
            }
        updated = process_event_photo_assets(
            db,
            document_storage_dir,
            event=event,
            include_processed=include_processed,
            max_items=max_items_per_event,
        )
        return {
            "events_processed": 1,
            "photos_processed": len(updated),
            "processed_asset_ids": [asset.id for asset in updated],
        }

    events_query = db.query(LifeEvent).order_by(LifeEvent.created_at.asc())
    if max_events is not None and max_events > 0:
        events = events_query.limit(max_events).all()
    else:
        events = events_query.all()

    processed_asset_ids: list[int] = []
    for event in events:
        updated = process_event_photo_assets(
            db,
            document_storage_dir,
            event=event,
            include_processed=include_processed,
            max_items=max_items_per_event,
        )
        processed_asset_ids.extend(asset.id for asset in updated)

    return {
        "events_processed": len(events),
        "photos_processed": len(processed_asset_ids),
        "processed_asset_ids": processed_asset_ids,
    }
