"""ffmpeg: normalise a recording to mono MP3 at 44.1 kHz and 128 kbps (v0's settings),
and measure its length. Missing or failing ffmpeg is reported, never raised: the
original recording is always kept and can still be transcribed."""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
ARGS = ["-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k", "-f", "mp3"]


@dataclass
class Normalised:
    ok: bool
    mp3: Path | None = None
    seconds: float | None = None
    problem: str | None = None


def duration(path: Path) -> float | None:
    if not shutil.which(FFPROBE):
        return None
    out = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    try:
        return round(float(json.loads(out.stdout)["format"]["duration"]), 2)
    except (ValueError, KeyError, TypeError):
        return None


def normalise(source: Path, target: Path) -> Normalised:
    if not shutil.which(FFMPEG):
        return Normalised(False, problem="ffmpeg is not installed")
    run = subprocess.run(
        [
            FFMPEG,
            "-nostdin",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            *ARGS,
            str(target),
        ],
        capture_output=True,
        text=True,
        timeout=60 * 60,
    )
    if run.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        detail = (run.stderr or "no output").strip().splitlines()[-1:] or ["failed"]
        return Normalised(False, problem=f"ffmpeg failed: {detail[0][:300]}")
    return Normalised(True, mp3=target, seconds=duration(target))
