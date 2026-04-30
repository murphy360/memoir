import base64
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import requests
from fastapi import HTTPException

from app.services.memory_analysis import MemoryMetadata, build_sort_date, normalize_string_list

logger = logging.getLogger("memoir.api")


@dataclass
class ResearchSource:
    title: str
    url: str


@dataclass
class ResearchResult:
    summary: str
    queries: list[str] = field(default_factory=list)
    sources: list[ResearchSource] = field(default_factory=list)


@dataclass
class DateSuggestion:
    estimated_date_text: str
    date_precision: str
    date_year: Optional[int]
    date_month: Optional[int]
    date_day: Optional[int]
    date_decade: Optional[int]
    reasoning: str


def suggest_date_from_research(
    research_summary: str,
    current_date_text: Optional[str],
    current_date_precision: Optional[str],
) -> Optional[DateSuggestion]:
    """Use Gemini function calling to extract date suggestion from research summary.

    Returns None if no meaningful improvement over the current date is found,
    or if the Gemini API key is unavailable.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return None

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "You are analyzing research results for a personal memory and extracting date refinements. "
                            "Read the research summary and suggest an improved date if the evidence is clear. "
                            "If no meaningful improvement is possible, call suggest_date_refinement with no arguments (or empty args). "
                            "Current recorded date: {current_date_text or 'Unknown'}\n"
                            "Current precision: {current_date_precision or 'unknown'}\n\n"
                            f"Research summary:\n{research_summary}"
                        )
                    }
                ]
            }
        ],
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": "suggest_date_refinement",
                        "description": "Suggest a refined date for a memory based on research findings. Leave all fields null if no refinement is warranted.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "estimated_date_text": {"type": "string"},
                                "date_precision": {
                                    "type": "string",
                                    "enum": ["exact", "approximate", "month", "year", "decade"],
                                },
                                "date_year": {"type": "integer"},
                                "date_month": {"type": "integer"},
                                "date_day": {"type": "integer"},
                                "date_decade": {"type": "integer"},
                                "reasoning": {"type": "string"},
                            },
                            "required": [],
                        },
                    }
                ]
            }
        ],
        "toolConfig": {
            "functionCallingConfig": {
                "mode": "ANY",
                "allowedFunctionNames": ["suggest_date_refinement"],
            }
        },
    }

    try:
        response = requests.post(endpoint, params={"key": gemini_key}, json=payload, timeout=30)
        if not response.ok:
            logger.warning("Date suggestion request failed: %s", response.text[:200])
            return None
        data = response.json()
    except Exception as exc:
        logger.warning("Date suggestion exception: %s", exc)
        return None

    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for part in parts:
        function_call = part.get("functionCall")
        if not function_call or function_call.get("name") != "suggest_date_refinement":
            continue

        args = function_call.get("args", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}

        # If no estimated_date_text, no suggestion to make
        estimated_date_text = str(args.get("estimated_date_text") or "").strip()
        if not estimated_date_text:
            return None

        return DateSuggestion(
            estimated_date_text=estimated_date_text[:100],
            date_precision=str(args.get("date_precision") or "approximate"),
            date_year=_int_or_none(args.get("date_year")),
            date_month=_int_or_none(args.get("date_month")),
            date_day=_int_or_none(args.get("date_day")),
            date_decade=_int_or_none(args.get("date_decade")),
            reasoning=str(args.get("reasoning") or "")[:500],
        )

    return None


def _int_or_none(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def generate_research_questions(
    research_summary: str,
    event_description: str,
    referenced_people: list[str],
) -> list[str]:
    """Generate 2-3 follow-up research questions based on findings.
    
    Uses Gemini to extract the most important unanswered questions or entities
    worth exploring further from the research summary.
    """
    logger.info("GENERATE_RESEARCH_QUESTIONS called with event: %s, num_people: %d", event_description[:50], len(referenced_people))
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        logger.warning("No GEMINI_API_KEY found")
        return []

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Based on this research summary, generate 2-3 specific follow-up questions "
                            "that would help deepen understanding of the memory. "
                            "Focus on:\n"
                            "- Key people or organizations mentioned that deserve deeper investigation\n"
                            "- Important events or situations referenced that warrant their own memory\n"
                            "- Gaps or contradictions that need clarification\n"
                            "- Related events that might connect to other memories\n\n"
                            "Each question should be concrete, answerable, and directly connected to something in the research.\n\n"
                            "IMPORTANT: Return exactly 2-3 complete questions, one per line, with NO numbering, bullets, or extra text. "
                            "Each line must be a complete question ending with a question mark.\n\n"
                            f"Original event: {event_description}\n"
                            f"Research findings:\n{research_summary}"
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 500,
        },
    }

    try:
        response = requests.post(endpoint, params={"key": gemini_key}, json=payload, timeout=30)
        if not response.ok:
            logger.warning("Research questions request failed: %s", response.text[:200])
            return []
        data = response.json()
        candidate = data.get("candidates", [{}])[0]
        parts = candidate.get("content", {}).get("parts", [])
        text = "\n".join(part.get("text", "").strip() for part in parts if part.get("text")).strip()
        logger.info("Research questions raw response: %s", text[:300])
        if not text:
            logger.warning("Research questions returned empty text")
            return []
        # Split by newline, filter empty lines, and keep only lines ending with ?
        all_lines = [q.strip() for q in text.split("\n") if q.strip()]
        logger.info("All extracted lines: %s", all_lines)
        questions = [q for q in all_lines if q.endswith("?")]
        logger.info("Questions with question marks: %s", questions)
        return questions[:3]  # Return at most 3 questions
    except Exception as exc:
        logger.warning("Generate research questions exception: %s", exc)
        return []


def research_memory_details(
    transcript: str,
    event_description: str,
    estimated_date_text: Optional[str],
    referenced_locations: list[str],
    referenced_people: list[str],
) -> ResearchResult:
    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_RESEARCH_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    location_text = ", ".join(referenced_locations) if referenced_locations else "Unknown"
    people_text = ", ".join(referenced_people) if referenced_people else "Unknown"

    if gemini_key:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Research this personal memory using multiple targeted Google Search queries to uncover details. "
                                "Conduct systematic searches for: people named/implied, organizations/units, locations, and events at that date/place.\n\n"
                                "For EACH person, organization, or entity mentioned:\n"
                                "1. Search them individually (e.g., 'John Smith military' or 'USS Lake Erie 2014')\n"
                                "2. Look for leadership changes, departures, or notable incidents\n"
                                "3. Find biographical/organizational details that might corroborate the memory\n\n"
                                "For the DATE + LOCATION combination:\n"
                                "- Search for major events, operations, news at that specific time/place\n"
                                "- Look for organizational deployments or maintenance schedules\n"
                                "- Find historical patterns or recurring events (if repeating annually, etc.)\n\n"
                                "Structure your response with these sections:\n"
                                "- 'Key findings': The most significant corroborating or contextual details discovered\n"
                                "- 'People/organizations involved': Names, roles, and any notable history found\n"
                                "- 'Historical context': What was happening at that time/place more broadly\n"
                                "- 'Unknowns to verify': What still needs confirmation\n\n"
                                "Only claim facts that can be supported by search results. If information is incomplete, say so explicitly. "
                                "Flag any claims that could queue up follow-up memories or additional research.\n\n"
                                f"Event description: {event_description}\n"
                                f"Estimated date: {estimated_date_text or 'Unknown'}\n"
                                f"Referenced locations: {location_text}\n"
                                f"Referenced people: {people_text}\n"
                                f"Transcript:\n{transcript}"
                            )
                        }
                    ]
                }
            ],
            "tools": [
                {
                    "googleSearch": {
                        "searchTypes": {
                            "webSearch": {}
                        }
                    }
                }
            ],
            "generationConfig": {
                "temperature": 0.15,
                "maxOutputTokens": 1200,
                "responseMimeType": "text/plain"
            }
        }

        try:
            response = requests.post(endpoint, params={"key": gemini_key}, json=payload, timeout=30)
            if response.ok:
                data = response.json()
                candidate = data.get("candidates", [{}])[0]
                text_parts = candidate.get("content", {}).get("parts", [])
                text = "\n".join(part.get("text", "").strip() for part in text_parts if part.get("text")).strip()
                if text:
                    grounding = candidate.get("groundingMetadata", {})
                    queries = _extract_grounding_queries(grounding)
                    sources = _extract_grounding_sources(grounding)
                    return ResearchResult(summary=text[:4000], queries=queries, sources=sources)
            else:
                logger.warning("Gemini research request failed: %s", response.text[:300])
        except Exception as exc:
            logger.warning("Gemini research request exception: %s", exc)

    lead = event_description.strip() or "This memory"
    bullets: list[str] = [
        "Key findings",
        f"- {lead} occurred around {estimated_date_text or 'an unknown date'}.",
    ]
    if referenced_people:
        bullets.append(
            f"- Key people mentioned: {', '.join(referenced_people)}. Search each individually to find biographical details, military records, employment history, or public mentions around that timeframe."
        )
    if referenced_locations:
        bullets.append(
            f"- Locations to research: {', '.join(referenced_locations)}. Look for local archives, newspapers from that era, town/county historical societies, and institutional records."
        )
    
    bullets.extend(
        [
            "",
            "People/organizations involved",
            "- Any named individuals should be researched individually (name + relevant context like military, school, company, etc.)",
            "- Organizations or units mentioned (military units, companies, agencies, schools) benefit from dedicated searches on their history and leadership during that period.",
        ]
    )
    
    bullets.extend(
        [
            "",
            "Historical context",
            f"- Events in {estimated_date_text or 'that era'} at {', '.join(referenced_locations) or 'those locations'} may have been tied to larger historical events, deployments, policy changes, or public incidents.",
            "- Consider what was happening more broadly (nationally, locally, in that organization) at that exact time.",
            "",
            "Unknowns to verify",
            "- Specific dates, names, and organizational details can help narrow down corroborating sources.",
            "- Any named person or organizational unit warrants a targeted search.",
        ]
    )
    fallback_sources: list[ResearchSource] = []
    if referenced_locations:
        fallback_sources.append(
            ResearchSource(
                title="Local records and archives",
                url="https://www.google.com/search?q=" + requests.utils.quote(f"{' '.join(referenced_locations)} history {estimated_date_text or ''}"),
            )
        )
    if referenced_people:
        fallback_sources.append(
            ResearchSource(
                title="People search",
                url="https://www.google.com/search?q=" + requests.utils.quote(f"{' '.join(referenced_people)} {estimated_date_text or ''}"),
            )
        )
    fallback_sources.append(
        ResearchSource(
            title="General event search",
            url="https://www.google.com/search?q=" + requests.utils.quote(f"{event_description} {estimated_date_text or ''}"),
        )
    )
    if "scout" in transcript.lower() or "pack" in transcript.lower() or "troop" in transcript.lower():
        fallback_sources.append(
            ResearchSource(
                title="Scouting organization records",
                url="https://www.google.com/search?q=" + requests.utils.quote("scouting history council troops packs"),
            )
        )
    return ResearchResult(summary="\n".join(bullets)[:4000], sources=fallback_sources)


def _extract_grounding_queries(grounding: object) -> list[str]:
    if not isinstance(grounding, dict):
        return []
    queries = grounding.get("webSearchQueries")
    if not isinstance(queries, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for query in queries:
        if not isinstance(query, str):
            continue
        normalized = query.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result[:8]


def _extract_grounding_sources(grounding: object) -> list[ResearchSource]:
    if not isinstance(grounding, dict):
        return []
    chunks = grounding.get("groundingChunks")
    if not isinstance(chunks, list):
        return []

    sources: list[ResearchSource] = []
    seen: set[str] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        web = chunk.get("web")
        if not isinstance(web, dict):
            continue
        url = str(web.get("uri") or "").strip()
        title = str(web.get("title") or url).strip()
        if not url:
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        sources.append(ResearchSource(title=title[:200], url=url[:1000]))
    return sources[:8]


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
