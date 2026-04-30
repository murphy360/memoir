import base64
import json
import logging
import os
from typing import Optional

import requests
from fastapi import HTTPException

from app.services.memory_analysis import MemoryMetadata, build_sort_date, normalize_string_list

logger = logging.getLogger("memoir.api")


def transcribe_audio(filename: str, audio_bytes: bytes) -> str:
    allow_placeholder = os.getenv("ALLOW_PLACEHOLDER_TRANSCRIPT", "false").lower() == "true"
    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    failure_reasons: list[str] = []

    if gemini_key:
        mime_types = ["audio/webm", "audio/webm;codecs=opus", "audio/ogg", "audio/mpeg", "audio/wav", "audio/mp4"]
        if filename.lower().endswith(".wav"):
            mime_types = ["audio/wav"]
        elif filename.lower().endswith(".mp3"):
            mime_types = ["audio/mpeg"]
        elif filename.lower().endswith(".m4a"):
            mime_types = ["audio/mp4"]

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
        encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")

        for mime_type in mime_types:
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": "Transcribe this audio exactly. Return plain text only."},
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": encoded_audio,
                                }
                            },
                        ]
                    }
                ]
            }

            try:
                response = requests.post(endpoint, params={"key": gemini_key}, json=payload, timeout=45)
            except Exception as exc:
                failure_reasons.append(f"Gemini exception: {str(exc)}")
                logger.exception("Gemini transcription request failed")
                continue

            if not response.ok:
                failure_reasons.append(f"Gemini ({mime_type}) HTTP {response.status_code}: {response.text[:180]}")
                continue

            data = response.json()
            text_parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = " ".join(part.get("text", "") for part in text_parts).strip()
            if text:
                return text
            failure_reasons.append(f"Gemini ({mime_type}) returned empty transcription")

    if allow_placeholder:
        return (
            "My name is Alex. I remember last summer when my family and I drove our red car "
            "to the coast near Brighton. It felt joyful, but I cannot remember exactly what happened first."
        )

    raise HTTPException(
        status_code=502,
        detail=(
            "Transcription failed. Configure GEMINI_API_KEY to enable speech-to-text "
            "or set ALLOW_PLACEHOLDER_TRANSCRIPT=true for demo mode. "
            f"Details: {' | '.join(failure_reasons)[:800]}"
        ),
    )


def extract_metadata_with_gemini_function_call(transcript: str) -> Optional[MemoryMetadata]:
    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if not gemini_key:
        return None

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Extract structured metadata from this memoir transcript. "
                            "You must call set_memory_metadata exactly once. "
                            "Use best-effort date precision: day, month, year, decade, approximate, or unknown. "
                            "Transcript:\n"
                            f"{transcript}"
                        )
                    }
                ]
            }
        ],
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": "set_memory_metadata",
                        "description": "Set recorder, date granularity, and referenced people/locations for one memory.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date_text": {"type": "string"},
                                "date_precision": {
                                    "type": "string",
                                    "enum": ["day", "month", "year", "decade", "approximate", "unknown"],
                                },
                                "date_year": {"type": "integer"},
                                "date_month": {"type": "integer"},
                                "date_day": {"type": "integer"},
                                "date_decade": {"type": "integer"},
                                "recorder_name": {"type": "string"},
                                "people": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "locations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["date_text", "date_precision", "people", "locations"],
                        },
                    }
                ]
            }
        ],
        "toolConfig": {
            "functionCallingConfig": {
                "mode": "ANY",
                "allowedFunctionNames": ["set_memory_metadata"],
            }
        },
    }

    try:
        response = requests.post(endpoint, params={"key": gemini_key}, json=payload, timeout=30)
        if not response.ok:
            logger.warning("Gemini metadata extraction failed: %s", response.text[:300])
            return None
        data = response.json()
    except Exception as exc:
        logger.warning("Gemini metadata request exception: %s", exc)
        return None

    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for part in parts:
        function_call = part.get("functionCall")
        if not function_call or function_call.get("name") != "set_memory_metadata":
            continue

        args = function_call.get("args", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}

        date_precision = str(args.get("date_precision") or "unknown").strip().lower()
        if date_precision not in {"day", "month", "year", "decade", "approximate", "unknown"}:
            date_precision = "unknown"

        date_year = _safe_int(args.get("date_year"))
        date_month = _safe_int(args.get("date_month"))
        date_day = _safe_int(args.get("date_day"))
        date_decade = _safe_int(args.get("date_decade"))

        sort_date = build_sort_date(date_precision, date_year, date_month, date_day, date_decade)
        people = normalize_string_list(_safe_string_list(args.get("people")))
        locations = normalize_string_list(_safe_string_list(args.get("locations")))

        recorder_name = str(args.get("recorder_name") or "").strip() or None
        date_text = str(args.get("date_text") or "unknown").strip() or "unknown"

        return MemoryMetadata(
            date_text=date_text[:100],
            date_precision=date_precision,
            sort_date=sort_date,
            date_year=date_year,
            date_month=date_month,
            date_day=date_day,
            date_decade=date_decade,
            recorder_name=recorder_name,
            people=people,
            locations=locations,
        )

    return None


def _safe_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
    return result
