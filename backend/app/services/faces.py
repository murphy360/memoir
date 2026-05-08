"""Face detection and event face projection helpers.

This module intentionally does detection-only for phase 1: we store face regions
per photo asset and allow manual person assignment later.
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


MIN_FACE_SIZE_PX = 48
MIN_FACE_AREA_RATIO = 0.004
MAX_FACE_AREA_RATIO = 0.45
MIN_FACE_ASPECT_RATIO = 0.62
MAX_FACE_ASPECT_RATIO = 1.6
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
    """Detect frontal faces and return normalized bounding boxes.

    Coordinates are normalized to [0, 1] based on decoded image dimensions,
    so the frontend can crop consistently regardless of photo size.
    """
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
    if compreface_faces is not None:
        return _dedupe_overlapping_faces(compreface_faces)

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    if detector.empty():
        return []

    detections = detector.detectMultiScale(
        gray,
        scaleFactor=1.08,
        minNeighbors=7,
        minSize=(MIN_FACE_SIZE_PX, MIN_FACE_SIZE_PX),
    )

    faces: list[FaceDetection] = []
    for x, y, w, h in detections:
        if w <= 0 or h <= 0:
            continue

        area_ratio = (w * h) / float(width * height)
        aspect_ratio = w / float(h)
        if area_ratio < MIN_FACE_AREA_RATIO or area_ratio > MAX_FACE_AREA_RATIO:
            continue
        if aspect_ratio < MIN_FACE_ASPECT_RATIO or aspect_ratio > MAX_FACE_ASPECT_RATIO:
            continue

        faces.append(
            FaceDetection(
                bbox_x=max(0.0, min(1.0, x / width)),
                bbox_y=max(0.0, min(1.0, y / height)),
                bbox_w=max(0.0, min(1.0, w / width)),
                bbox_h=max(0.0, min(1.0, h / height)),
                confidence=None,
            )
        )

    return _dedupe_overlapping_faces(faces)


def _detect_faces_with_compreface(*, image_bytes: bytes, width: int, height: int) -> Optional[list[FaceDetection]]:
    """Detect faces via CompreFace; return None when unavailable to allow fallback."""
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        return None

    try:
        response = requests.post(
            f"{COMPREFACE_BASE_URL}/api/v1/recognition/recognize",
            headers={"x-api-key": COMPREFACE_API_KEY},
            params={
                # Keep at least one match so recognized subjects are returned.
                "limit": max(1, COMPREFACE_PREDICTION_COUNT),
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
        logger.warning("CompreFace request failed; falling back to OpenCV: %s", exc)
        return None
    except ValueError as exc:
        logger.warning("CompreFace JSON parse failed; falling back to OpenCV: %s", exc)
        return None

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

        area_ratio = (w * h) / float(width * height)
        aspect_ratio = w / h
        if area_ratio < MIN_FACE_AREA_RATIO or area_ratio > MAX_FACE_AREA_RATIO:
            continue
        if aspect_ratio < MIN_FACE_ASPECT_RATIO or aspect_ratio > MAX_FACE_ASPECT_RATIO:
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


def assign_face_to_person(db: Session, face_id: int, person_id: Optional[int]) -> AssetFace:
    """Assign a detected face to a person, or clear assignment with null."""
    face = db.get(AssetFace, face_id)
    if face is None:
        raise ValueError("face_not_found")

    if person_id is None:
        face.person_id = None
        return face

    person = db.get(Person, person_id)
    if person is None:
        raise ValueError("person_not_found")

    face.person_id = person.id
    return face
