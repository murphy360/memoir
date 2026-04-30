import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, UploadFile


def guess_audio_extension(filename: str, content_type: Optional[str]) -> str:
    lower_name = filename.lower()
    if "." in lower_name:
        candidate = lower_name.rsplit(".", 1)[1]
        if candidate in {"webm", "wav", "mp3", "m4a", "ogg"}:
            return f".{candidate}"

    content_map = {
        "audio/webm": ".webm",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
    }
    return content_map.get((content_type or "").lower(), ".webm")


def save_audio_file(upload: UploadFile, audio_bytes: bytes, storage_dir: Path) -> tuple[str, str, int, bytes]:
    source_extension = guess_audio_extension(upload.filename or "recording.webm", upload.content_type)

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(temp_dir) / f"input{source_extension}"
        output_path = Path(temp_dir) / "output.mp3"

        input_path.write_bytes(audio_bytes)

        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-b:a",
            "128k",
            str(output_path),
        ]

        try:
            process = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail="FFmpeg is not installed on the backend container") from exc

        if process.returncode != 0 or not output_path.exists():
            error_text = (process.stderr or process.stdout or "Unknown FFmpeg error").strip()
            raise HTTPException(status_code=500, detail=f"Failed to convert audio to MP3: {error_text[:300]}")

        mp3_bytes = output_path.read_bytes()

    stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex}.mp3"
    file_path = storage_dir / stored_name
    file_path.write_bytes(mp3_bytes)
    return stored_name, "audio/mpeg", len(mp3_bytes), mp3_bytes
