"""
Standalone test: verify GPS EXIF extraction from a real photo.

Usage (from the backend/ directory):
    python test_exif_gps.py [path/to/photo.jpg]

If no path is provided it defaults to the photo below.
"""

import sys
from pathlib import Path

# ── allow running from either repo root or backend/ ──────────────────────────
_here = Path(__file__).resolve().parent
sys.path.insert(0, str(_here))

from app.services.image_metadata import extract_image_metadata  # noqa: E402

DEFAULT_PHOTO = Path(r"C:\Users\corey.murphy\Downloads\20240618_115059.jpg")


def run(photo_path: Path) -> None:
    if not photo_path.exists():
        raise FileNotFoundError(f"Photo not found: {photo_path}")

    file_bytes = photo_path.read_bytes()
    content_type = "image/jpeg"

    print(f"Parsing EXIF from: {photo_path}")
    meta = extract_image_metadata(file_bytes, content_type)

    # ── GPS assertions ────────────────────────────────────────────────────────
    assert meta.gps_latitude is not None, "FAIL: gps_latitude is None — GPS data not parsed"
    assert meta.gps_longitude is not None, "FAIL: gps_longitude is None — GPS data not parsed"
    assert -90.0 <= meta.gps_latitude <= 90.0, f"FAIL: latitude out of range: {meta.gps_latitude}"
    assert -180.0 <= meta.gps_longitude <= 180.0, f"FAIL: longitude out of range: {meta.gps_longitude}"

    # ── Print all extracted fields ────────────────────────────────────────────
    print(f"  gps_latitude   : {meta.gps_latitude}")
    print(f"  gps_longitude  : {meta.gps_longitude}")
    print(f"  captured_at    : {meta.captured_at}")
    print(f"  captured_at_txt: {meta.captured_at_text}")
    print(f"  camera_make    : {meta.camera_make}")
    print(f"  camera_model   : {meta.camera_model}")
    print(f"  lens_model     : {meta.lens_model}")
    print(f"  orientation    : {meta.orientation}")
    print(f"  image_width    : {meta.image_width}")
    print(f"  image_height   : {meta.image_height}")
    print(f"  exif_json      : {'<present>' if meta.exif_json else None}")

    print("\nAll GPS assertions passed.")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PHOTO
    run(path)
