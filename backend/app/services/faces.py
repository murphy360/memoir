"""Face detection and event face projection helpers.

This module intentionally does detection-only for phase 1: we store face regions
per photo asset and allow manual person assignment later.
"""

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.models import Asset, AssetFace, EventAsset, Person


MIN_FACE_SIZE_PX = 48
MIN_FACE_AREA_RATIO = 0.004
MAX_FACE_AREA_RATIO = 0.45
MIN_FACE_ASPECT_RATIO = 0.62
MAX_FACE_ASPECT_RATIO = 1.6


@dataclass
class FaceDetection:
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    confidence: Optional[float] = None


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


def replace_asset_faces(db: Session, asset: Asset, detections: list[FaceDetection]) -> None:
    """Replace stored face boxes for a photo asset from latest detection output."""
    for face in list(asset.faces):
        db.delete(face)

    for detection in detections:
        db.add(
            AssetFace(
                asset_id=asset.id,
                bbox_x=detection.bbox_x,
                bbox_y=detection.bbox_y,
                bbox_w=detection.bbox_w,
                bbox_h=detection.bbox_h,
                confidence=detection.confidence,
                person_id=None,
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
