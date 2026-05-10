"""Face detection and event face projection helpers.

Detection is CompreFace-only. Legacy OpenCV Haar cascade detection has been
removed from the runtime path.

Face Enrollment Workflow:
  When an unknown face (compreface_subject is None) is manually assigned to a person for the first time,
  the face is automatically enrolled into a new CompreFace subject. This enables future automatic
  recognition of that person's face pattern. Subject names are kept in sync when people are renamed.
"""

from dataclasses import dataclass
import json
import logging
import os
from typing import Any, Optional

import cv2
import numpy as np
import requests
from sqlalchemy.orm import Session

from app.models import Asset, AssetFace, EventAsset, Person, PersonAlias
from app.services.periods import normalize_directory_name


COMPREFACE_API_KEY = (os.getenv("COMPREFACE_API_KEY") or "").strip()
COMPREFACE_BASE_URL = (os.getenv("COMPREFACE_BASE_URL") or "http://compreface-api:8080").strip().rstrip("/")
COMPREFACE_TIMEOUT_SECONDS = float(os.getenv("COMPREFACE_TIMEOUT_SECONDS", "6.0"))
COMPREFACE_DET_PROB_THRESHOLD = os.getenv("COMPREFACE_DET_PROB_THRESHOLD", "0.75").strip()
COMPREFACE_PREDICTION_COUNT = int(os.getenv("COMPREFACE_PREDICTION_COUNT", "3"))
COMPREFACE_FACE_PLUGINS = (os.getenv("COMPREFACE_FACE_PLUGINS") or "").strip()
FACE_DETECTION_ON_INGEST = os.getenv("FACE_DETECTION_ON_INGEST", "true").strip().lower() not in ("false", "0", "no")
COMPREFACE_AUTO_ASSIGN_ENABLED = os.getenv("COMPREFACE_AUTO_ASSIGN_ENABLED", "true").strip().lower() not in ("false", "0", "no")
COMPREFACE_AUTO_ASSIGN_MIN_SIMILARITY = float(os.getenv("COMPREFACE_AUTO_ASSIGN_MIN_SIMILARITY", "0.92"))

logger = logging.getLogger("memoir.faces")


@dataclass
class FaceDetection:
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    confidence: Optional[float] = None
    compreface_subject: Optional[str] = None
    compreface_similarity: Optional[float] = None
    compreface_gender: Optional[str] = None
    compreface_age_low: Optional[int] = None
    compreface_age_high: Optional[int] = None
    compreface_raw: Optional[dict[str, Any]] = None


def detect_faces_from_image(image_bytes: bytes) -> list[FaceDetection]:
    """Detect faces and return normalized bounding boxes using CompreFace only."""
    if not image_bytes:
        return []

    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if frame is None:
        return []

    height, width = frame.shape[:2]
    if width <= 0 or height <= 0:
        return []

    compreface_faces = _detect_faces_with_compreface(
        image_bytes=image_bytes,
        width=width,
        height=height,
    )
    deduped = _dedupe_overlapping_faces(compreface_faces)
    return _dedupe_subject_matches(deduped)


def _detect_faces_with_compreface(*, image_bytes: bytes, width: int, height: int) -> list[FaceDetection]:
    """Detect faces via CompreFace only; return empty list on error/unavailable."""
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        logger.warning("CompreFace is not configured; skipping face detection.")
        return []

    try:
        response = requests.post(
            f"{COMPREFACE_BASE_URL}/api/v1/recognition/recognize",
            headers={"x-api-key": COMPREFACE_API_KEY},
            params={
                # limit = max faces returned per image (not subject matches per face).
                # Set high so large group photos are fully detected.
                "limit": 50,
                # prediction_count = max subject candidates returned per detected face.
                "prediction_count": max(1, COMPREFACE_PREDICTION_COUNT),
                "det_prob_threshold": COMPREFACE_DET_PROB_THRESHOLD,
                **({"face_plugins": COMPREFACE_FACE_PLUGINS} if COMPREFACE_FACE_PLUGINS else {}),
                "status": "false",
                "detect_faces": "true",
            },
            files={"file": ("image.jpg", image_bytes, "image/jpeg")},
            timeout=COMPREFACE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("CompreFace request failed; face detection skipped: %s", exc)
        return []
    except ValueError as exc:
        logger.warning("CompreFace JSON parse failed; face detection skipped: %s", exc)
        return []

    result_items = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result_items, list):
        return []

    faces: list[FaceDetection] = []
    for item in result_items:
        if not isinstance(item, dict):
            continue
        box = item.get("box")
        if not isinstance(box, dict):
            continue

        x_min = box.get("x_min")
        y_min = box.get("y_min")
        x_max = box.get("x_max")
        y_max = box.get("y_max")
        if None in (x_min, y_min, x_max, y_max):
            continue

        try:
            x = float(x_min)
            y = float(y_min)
            w = float(x_max) - float(x_min)
            h = float(y_max) - float(y_min)
        except (TypeError, ValueError):
            continue

        if w <= 0.0 or h <= 0.0:
            continue

        probability = box.get("probability")
        confidence: Optional[float] = None
        try:
            confidence = float(probability) if probability is not None else None
        except (TypeError, ValueError):
            confidence = None

        top_subject: Optional[str] = None
        top_similarity: Optional[float] = None
        subjects = item.get("subjects")
        if isinstance(subjects, list):
            for candidate in subjects:
                if not isinstance(candidate, dict):
                    continue
                candidate_subject = candidate.get("subject")
                candidate_similarity = candidate.get("similarity")
                if not isinstance(candidate_subject, str):
                    continue
                try:
                    similarity_value = float(candidate_similarity)
                except (TypeError, ValueError):
                    continue
                if top_similarity is None or similarity_value > top_similarity:
                    top_similarity = similarity_value
                    top_subject = candidate_subject

        compreface_gender: Optional[str] = None
        gender = item.get("gender")
        if isinstance(gender, dict) and isinstance(gender.get("value"), str):
            compreface_gender = str(gender.get("value"))

        compreface_age_low: Optional[int] = None
        compreface_age_high: Optional[int] = None
        age = item.get("age")
        if isinstance(age, dict):
            try:
                compreface_age_low = int(age.get("low")) if age.get("low") is not None else None
            except (TypeError, ValueError):
                compreface_age_low = None
            try:
                compreface_age_high = int(age.get("high")) if age.get("high") is not None else None
            except (TypeError, ValueError):
                compreface_age_high = None

        faces.append(
            FaceDetection(
                bbox_x=max(0.0, min(1.0, x / width)),
                bbox_y=max(0.0, min(1.0, y / height)),
                bbox_w=max(0.0, min(1.0, w / width)),
                bbox_h=max(0.0, min(1.0, h / height)),
                confidence=confidence,
                compreface_subject=top_subject,
                compreface_similarity=top_similarity,
                compreface_gender=compreface_gender,
                compreface_age_low=compreface_age_low,
                compreface_age_high=compreface_age_high,
                compreface_raw=item,
            )
        )

    return faces


def _face_iou(left: FaceDetection, right: FaceDetection) -> float:
    left_x2 = left.bbox_x + left.bbox_w
    left_y2 = left.bbox_y + left.bbox_h
    right_x2 = right.bbox_x + right.bbox_w
    right_y2 = right.bbox_y + right.bbox_h

    inter_x1 = max(left.bbox_x, right.bbox_x)
    inter_y1 = max(left.bbox_y, right.bbox_y)
    inter_x2 = min(left_x2, right_x2)
    inter_y2 = min(left_y2, right_y2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0.0:
        return 0.0

    left_area = left.bbox_w * left.bbox_h
    right_area = right.bbox_w * right.bbox_h
    denom = (left_area + right_area - inter_area)
    if denom <= 0.0:
        return 0.0
    return inter_area / denom


def _dedupe_overlapping_faces(faces: list[FaceDetection]) -> list[FaceDetection]:
    if len(faces) <= 1:
        return faces

    kept: list[FaceDetection] = []
    for face in sorted(faces, key=lambda item: item.bbox_w * item.bbox_h, reverse=True):
        if any(_face_iou(face, existing) > 0.42 for existing in kept):
            continue
        kept.append(face)
    return kept


def _dedupe_subject_matches(faces: list[FaceDetection]) -> list[FaceDetection]:
    """For each recognized subject, keep only the highest-similarity match.

    If the same subject appears multiple times (e.g. a group photo where one
    person's face is detected in two positions), only the best match keeps the
    subject label. All lower-confidence duplicates are cleared to unknown so
    they surface in the unrecognized-faces inbox rather than creating false
    assignments.
    """
    # Find the highest similarity seen for each subject
    best_similarity: dict[str, float] = {}
    for face in faces:
        if face.compreface_subject and face.compreface_similarity is not None:
            current_best = best_similarity.get(face.compreface_subject)
            if current_best is None or face.compreface_similarity > current_best:
                best_similarity[face.compreface_subject] = face.compreface_similarity

    # Track which subjects have already claimed their best slot
    claimed: set[str] = set()
    result: list[FaceDetection] = []
    for face in faces:
        subject = face.compreface_subject
        if not subject:
            # Unknown face — keep as-is
            result.append(face)
        elif (
            face.compreface_similarity is not None
            and face.compreface_similarity == best_similarity.get(subject)
            and subject not in claimed
        ):
            # Best match for this subject — keep it and claim the slot
            claimed.add(subject)
            result.append(face)
        else:
            # Non-best or duplicate match — downgrade to unknown
            result.append(
                FaceDetection(
                    bbox_x=face.bbox_x,
                    bbox_y=face.bbox_y,
                    bbox_w=face.bbox_w,
                    bbox_h=face.bbox_h,
                    confidence=face.confidence,
                    compreface_subject=None,
                    compreface_similarity=None,
                    compreface_gender=face.compreface_gender,
                    compreface_age_low=face.compreface_age_low,
                    compreface_age_high=face.compreface_age_high,
                    compreface_raw=face.compreface_raw,
                )
            )
    return result


def _resolve_person_id_for_subject(db: Session, subject: Optional[str]) -> Optional[int]:
    """Resolve a CompreFace subject string to exactly one existing Person id.

    Matching checks both canonical person names and person aliases.
    Returns None when the subject is blank or maps ambiguously to multiple people.
    """
    normalized = normalize_directory_name(subject)
    if not normalized:
        return None

    key = normalized.casefold()
    candidate_ids: set[int] = set()

    for person in db.query(Person).all():
        if person.name.casefold() == key:
            candidate_ids.add(person.id)

    alias_rows = db.query(PersonAlias).filter(PersonAlias.alias.ilike(normalized)).all()
    for alias in alias_rows:
        candidate_ids.add(alias.person_id)

    if len(candidate_ids) == 1:
        return next(iter(candidate_ids))
    return None


def replace_asset_faces(db: Session, asset: Asset, detections: list[FaceDetection]) -> None:
    """Replace stored face boxes for a photo asset from latest detection output."""
    for face in list(asset.faces):
        db.delete(face)

    for detection in detections:
        auto_person_id: Optional[int] = None
        if (
            COMPREFACE_AUTO_ASSIGN_ENABLED
            and detection.compreface_subject
            and detection.compreface_similarity is not None
            and detection.compreface_similarity >= COMPREFACE_AUTO_ASSIGN_MIN_SIMILARITY
        ):
            auto_person_id = _resolve_person_id_for_subject(db, detection.compreface_subject)

        db.add(
            AssetFace(
                asset_id=asset.id,
                bbox_x=detection.bbox_x,
                bbox_y=detection.bbox_y,
                bbox_w=detection.bbox_w,
                bbox_h=detection.bbox_h,
                confidence=detection.confidence,
                compreface_subject=detection.compreface_subject,
                compreface_similarity=detection.compreface_similarity,
                compreface_gender=detection.compreface_gender,
                compreface_age_low=detection.compreface_age_low,
                compreface_age_high=detection.compreface_age_high,
                compreface_raw_json=(json.dumps(detection.compreface_raw) if detection.compreface_raw else None),
                person_id=auto_person_id,
            )
        )


def sync_asset_faces_for_photo(db: Session, asset: Asset, image_bytes: bytes) -> None:
    """Run detection for a photo asset and replace face boxes in one call."""
    replace_asset_faces(db, asset, detect_faces_from_image(image_bytes))


def list_faces_for_event(db: Session, event_id: int) -> list[AssetFace]:
    """Return all detected faces from photo assets linked to one event."""
    return (
        db.query(AssetFace)
        .join(Asset, Asset.id == AssetFace.asset_id)
        .join(EventAsset, EventAsset.asset_id == Asset.id)
        .filter(EventAsset.event_id == event_id)
        .order_by(AssetFace.created_at.desc(), AssetFace.id.desc())
        .all()
    )


def create_compreface_subject(name: str) -> Optional[str]:
    """Create a new subject (person) in CompreFace and return the subject UUID.
    
    Returns None on error or if CompreFace is not configured.
    Raises requests.RequestException on API errors.
    """
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        logger.warning("CompreFace not configured; cannot create subject.")
        return None

    try:
        response = requests.post(
            f"{COMPREFACE_BASE_URL}/api/v1/recognition/subjects",
            headers={"x-api-key": COMPREFACE_API_KEY},
            json={"subject": name},
            timeout=COMPREFACE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        subject_id = payload.get("subject_id")
        if isinstance(subject_id, str) and subject_id:
            logger.info("Created CompreFace subject %s for %s", subject_id, name)
            return subject_id
        logger.warning("CompreFace subject creation returned no subject_id: %s", payload)
        return None
    except requests.RequestException as exc:
        logger.error("CompreFace subject creation failed: %s", exc)
        raise


def enroll_face_in_compreface_subject(subject_id: str, face_image_bytes: bytes) -> bool:
    """Add a face sample to a CompreFace subject for enrollment.
    
    Returns True on success, False on error or if CompreFace is not configured.
    Raises requests.RequestException on API errors.
    """
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        logger.warning("CompreFace not configured; cannot enroll face.")
        return False

    try:
        response = requests.post(
            f"{COMPREFACE_BASE_URL}/api/v1/recognition/faces",
            headers={"x-api-key": COMPREFACE_API_KEY},
            params={"subject_id": subject_id},
            files={"file": ("face.jpg", face_image_bytes, "image/jpeg")},
            timeout=COMPREFACE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        logger.info("Enrolled face into CompreFace subject %s", subject_id)
        return True
    except requests.RequestException as exc:
        logger.error("CompreFace face enrollment failed: %s", exc)
        raise


def rename_compreface_subject(subject_id: str, new_name: str) -> bool:
    """Rename a CompreFace subject.
    
    Returns True on success, False on error or if CompreFace is not configured.
    Raises requests.RequestException on API errors.
    """
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        logger.warning("CompreFace not configured; cannot rename subject.")
        return False

    try:
        response = requests.put(
            f"{COMPREFACE_BASE_URL}/api/v1/recognition/subjects/{subject_id}",
            headers={"x-api-key": COMPREFACE_API_KEY},
            json={"subject": new_name},
            timeout=COMPREFACE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        logger.info("Renamed CompreFace subject %s to %s", subject_id, new_name)
        return True
    except requests.RequestException as exc:
        logger.error("CompreFace subject rename failed: %s", exc)
        raise


def assign_face_to_person(db: Session, face_id: int, person_id: Optional[int]) -> AssetFace:
    """Assign a detected face to a person, or clear assignment with null.
    
    When assigning an unknown face (compreface_subject is None) to a person for the first time,
    automatically creates and enrolls the face in a CompreFace subject.
    """
    face = db.get(AssetFace, face_id)
    if face is None:
        raise ValueError("face_not_found")

    if person_id is None:
        face.person_id = None
        return face

    person = db.get(Person, person_id)
    if person is None:
        raise ValueError("person_not_found")

    # Auto-enroll unknown face to CompreFace if this is first assignment
    if (
        not face.compreface_subject
        and face.asset
        and face.asset.storage_filename
        and not person.compreface_subject_id
    ):
        try:
            from pathlib import Path
            from app.main import DOCUMENT_STORAGE_DIR
            
            file_path = DOCUMENT_STORAGE_DIR / face.asset.storage_filename
            if file_path.exists():
                image_bytes = file_path.read_bytes()
                # Create new CompreFace subject
                subject_id = create_compreface_subject(person.name)
                if subject_id:
                    person.compreface_subject_id = subject_id
                    # Enroll the face
                    if enroll_face_in_compreface_subject(subject_id, image_bytes):
                        logger.info("Auto-enrolled face for person %s (id=%s) to CompreFace subject %s", 
                                   person.name, person.id, subject_id)
        except Exception as exc:
            logger.warning("Face auto-enrollment to CompreFace failed; continuing without enrollment: %s", exc)

    face.person_id = person.id
    return face
