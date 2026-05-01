import re
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Asset, EventAsset, LifeEvent, LifePeriod, MemoryEntry
from app.schemas import AssetResponse, LifeEventResponse, LifePeriodAnalysisResponse, LifePeriodResponse
from app.services.gemini_client import generate_period_biography


def normalize_directory_name(value: Optional[str]) -> Optional[str]:
    candidate = (value or "").strip()
    if not candidate:
        return None
    if len(candidate) > 120:
        candidate = candidate[:120].rstrip()
    return candidate


def normalize_period_title(value: Optional[str]) -> Optional[str]:
    title = normalize_directory_name(value)
    if not title:
        return None
    if len(title) > 160:
        title = title[:160].rstrip()
    return title


def slugify_period_title(value: str) -> str:
    compact = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return compact[:180] or "period"


def unique_period_slug(db: Session, title: str, existing_id: Optional[int] = None) -> str:
    base = slugify_period_title(title)
    candidate = base
    suffix = 2
    while True:
        match = db.query(LifePeriod).filter(LifePeriod.slug == candidate).first()
        if not match or (existing_id is not None and match.id == existing_id):
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def build_period_response(period: LifePeriod) -> LifePeriodResponse:
    return LifePeriodResponse(
        id=period.id,
        title=period.title,
        slug=period.slug,
        start_date_text=period.start_date_text,
        end_date_text=period.end_date_text,
        summary=period.summary,
        event_count=len(period.events),
        asset_count=len(period.assets),
        created_at=period.created_at,
        updated_at=period.updated_at,
    )


def build_event_response(event: LifeEvent) -> LifeEventResponse:
    legacy_memory = event.legacy_memory

    return LifeEventResponse(
        id=event.id,
        period_id=event.period_id,
        title=event.title,
        description=event.description,
        event_date_text=event.event_date_text,
        date_precision=event.date_precision,
        date_year=event.date_year,
        date_month=event.date_month,
        date_day=event.date_day,
        date_decade=event.date_decade,
        legacy_memory_id=event.legacy_memory_id,
        legacy_audio_url=(legacy_memory.audio_url if legacy_memory else None),
        legacy_audio_size_bytes=(legacy_memory.audio_size_bytes if legacy_memory else None),
        linked_asset_count=len(event.linked_assets),
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def _extract_year_hint(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if not match:
        return None
    return int(match.group(1))


def _extract_year_hints(text: Optional[str]) -> list[int]:
    if not text:
        return []
    return [int(value) for value in re.findall(r"\b(19\d{2}|20\d{2})\b", text)]


def _period_bounds_in_years(period: LifePeriod) -> tuple[Optional[int], Optional[int]]:
    start_year = period.start_sort.year if period.start_sort else _extract_year_hint(period.start_date_text)
    end_year = period.end_sort.year if period.end_sort else _extract_year_hint(period.end_date_text)
    return start_year, end_year


def _event_year_bounds(events: list[LifeEvent]) -> tuple[Optional[int], Optional[int]]:
    years: list[int] = []
    for event in events:
        text_years = _extract_year_hints(event.event_date_text)
        if text_years:
            years.extend(text_years)

        if event.date_year:
            years.append(event.date_year)
            continue
        if event.date_decade:
            years.extend([event.date_decade, event.date_decade + 9])
            continue
        if event.event_date_sort:
            years.append(event.event_date_sort.year)
            continue

    if not years:
        return None, None
    return min(years), max(years)


def _recommended_period_dates_from_events(events: list[LifeEvent]) -> tuple[Optional[str], Optional[str], Optional[date], Optional[date]]:
    min_year, max_year = _event_year_bounds(events)
    if min_year is None or max_year is None:
        return None, None, None, None

    recommended_start_text = str(min_year)
    recommended_end_text = str(max_year)
    recommended_start_sort = date(min_year, 1, 1)
    recommended_end_sort = date(max_year, 12, 31)
    return recommended_start_text, recommended_end_text, recommended_start_sort, recommended_end_sort


def _is_generic_period_title(title: str) -> bool:
    normalized = (title or "").strip().lower()
    if not normalized:
        return True
    if normalized == "undated":
        return True
    if re.fullmatch(r"\d{4}", normalized):
        return True
    if re.fullmatch(r"\d{4}s", normalized):
        return True
    return False


_NARRATIVE_OPENERS = re.compile(
    r"^(i\s+)?(attended|went\s+to|started\s+(at|attending)?|enrolled\s+at|graduated\s+from|"
    r"transferred\s+to|moved\s+to|joined|was\s+(born|raised|stationed|deployed|assigned)\s+(in|at|to)?|"
    r"began\s+(working\s+at|at)?|took\s+a\s+job\s+at|worked\s+at|lived\s+(in|at)?|"
    r"returned\s+to|retired\s+from|left)\s+",
    re.IGNORECASE,
)
_TITLE_TAIL_STRIP = re.compile(r"\s+(in|at|to|from|for|and|the|a|an)$", re.IGNORECASE)


def _event_title_to_period_candidate(event_title: str, year_suffix: str) -> str | None:
    cleaned = _NARRATIVE_OPENERS.sub("", event_title.strip())
    cleaned = re.sub(
        r"\s+(from\s+\d{4}.*|in\s+(january|february|march|april|may|june|july|august|september|october|november|december|\d{4}).*|"
        r"during\s+\d{4}.*|until\s+\d{4}.*)$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = _TITLE_TAIL_STRIP.sub("", cleaned).strip()
    if len(cleaned) < 4 or cleaned == event_title.strip():
        return None
    cleaned = cleaned[:80]
    return f"{cleaned} {year_suffix}".strip()


def _suggest_period_titles(period: LifePeriod, events: list[LifeEvent]) -> tuple[list[str], str]:
    if not events:
        return [], "No events in this period yet, so there is no evidence to suggest a better title."

    min_year, max_year = _event_year_bounds(events)
    if min_year is None or max_year is None:
        return [], "Event dates are too uncertain to suggest a stronger period title."

    if min_year == max_year:
        year_suffix = f"({min_year})"
        decade_label = f"the {(min_year // 10) * 10}s"
    else:
        year_suffix = f"({min_year}\u2013{max_year})"
        if (min_year // 10) == (max_year // 10):
            decade_label = f"the {(min_year // 10) * 10}s"
        else:
            decade_label = f"the {(min_year // 10) * 10}s\u2013{(max_year // 10) * 10}s"

    haystack = " ".join(
        f"{event.title or ''} {event.description or ''}".lower()
        for event in events
    )

    candidates: list[str] = []

    for event in events[:3]:
        raw = (event.title or "").strip()
        if not raw:
            continue
        derived = _event_title_to_period_candidate(raw, year_suffix)
        if derived:
            candidates.append(derived)

    institution_hits: list[str] = []
    for keyword, label in [
        ("cathedral prep", "Cathedral Prep"),
        ("bishop mccort", "Bishop McCort"),
        ("central catholic", "Central Catholic"),
        ("north catholic", "North Catholic"),
        ("duquesne", "Duquesne University"),
        ("university of pittsburgh", "University of Pittsburgh"),
        ("pitt", "University of Pittsburgh"),
        ("carnegie mellon", "Carnegie Mellon"),
        ("penn state", "Penn State"),
        ("temple university", "Temple University"),
        ("ohio state", "Ohio State"),
        ("community college", "Community College"),
        ("bahrain", "Bahrain"),
        ("norfolk", "Norfolk Naval Station"),
        ("fort bragg", "Fort Bragg"),
        ("fort campbell", "Fort Campbell"),
    ]:
        if keyword in haystack:
            institution_hits.append(f"{label} {year_suffix}")
    candidates.extend(institution_hits)

    if any(tok in haystack for tok in ["elementary", "grade school", "primary school", "first grade", "second grade", "third grade", "fourth grade", "fifth grade"]):
        candidates.append(f"Elementary School Years {year_suffix}")
    if any(tok in haystack for tok in ["middle school", "junior high", "sixth grade", "seventh grade", "eighth grade"]):
        candidates.append(f"Middle School Years {year_suffix}")
    if any(tok in haystack for tok in ["high school", "ninth grade", "tenth grade", "eleventh grade", "twelfth grade", "prep school", "senior year", "prom", "homecoming"]):
        candidates.append(f"High School Years {year_suffix}")
    if any(tok in haystack for tok in ["university", "college", "undergraduate", "campus", "fraternity", "sorority"]):
        candidates.append(f"College Years {year_suffix}")
    if any(tok in haystack for tok in ["graduate school", "master", "phd", "doctorate", "dissertation", "thesis"]):
        candidates.append(f"Graduate Studies {year_suffix}")
    if any(tok in haystack for tok in ["deployment", "deployed", "mobilized", "mobilization"]):
        candidates.append(f"Overseas Deployment {year_suffix}")
    if any(tok in haystack for tok in ["navy", "army", "marine", "air force", "coast guard", "military", "enlisted"]):
        candidates.append(f"Military Service {year_suffix}")
    if any(tok in haystack for tok in ["married", "wedding", "engagement", "honeymoon"]):
        candidates.append(f"Marriage and Early Family {year_suffix}")
    if any(tok in haystack for tok in ["daughter", "son", "newborn", "baby", "pregnancy"]):
        candidates.append(f"Growing Our Family {year_suffix}")
    if any(tok in haystack for tok in ["scout", "troop", "eagle", "cub scout", "boy scout"]):
        candidates.append(f"Scouting Years {year_suffix}")
    if any(tok in haystack for tok in ["job", "career", "hired", "promotion", "manager", "engineer", "developer"]):
        candidates.append(f"Career Years {year_suffix}")
    if any(tok in haystack for tok in ["childhood", "born", "growing up", "playground"]):
        candidates.append(f"Early Childhood {year_suffix}")

    candidates.append(f"A Chapter from {decade_label}")

    current = period.title.strip()
    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        if candidate not in seen and candidate.lower() != current.lower():
            seen.add(candidate)
            unique.append(candidate)

    if not unique:
        return [], "The current title already reflects the events in this period."

    reasoning = (
        "The current title is generic. These candidates reflect the specific events and date range in this period."
        if _is_generic_period_title(period.title)
        else "These alternatives capture the themes and timeframe of events in this period."
    )
    return unique[:5], reasoning


def _generate_period_summary(period: LifePeriod, events: list[LifeEvent], asset_count: int) -> tuple[str, str]:
    if not events:
        return (
            "Auto-generated biography: This chapter is waiting for its first memory. As new moments and supporting materials are added, this biography-style summary will grow into a fuller life story.",
            "Summary generated from period structure because there are no events yet.",
        )

    min_year, max_year = _event_year_bounds(events)
    if min_year is None or max_year is None:
        range_text = "those years"
    elif min_year == max_year:
        range_text = str(min_year)
    else:
        range_text = f"{min_year} to {max_year}"

    event_titles = [(event.title or "").strip() for event in events if (event.title or "").strip()]
    event_descriptions = [(event.description or "").strip() for event in events]

    ai_text = generate_period_biography(
        period_title=period.title,
        year_range=range_text,
        event_titles=event_titles,
        event_descriptions=event_descriptions,
        asset_count=asset_count,
    )
    if ai_text:
        return f"Auto-generated biography: {ai_text}", "Summary written by AI from current events and linked assets."

    count = len(event_titles)
    if count == 0:
        event_line = "No events have been recorded for this period yet."
    elif count == 1:
        event_line = f"This chapter contains one recorded moment from {range_text}."
    else:
        event_line = f"This chapter covers {count} recorded moments spanning {range_text}."

    if asset_count == 0:
        asset_line = "No supporting photos or documents are linked yet."
    elif asset_count == 1:
        asset_line = "One supporting asset is linked to help tell the story."
    else:
        asset_line = f"{asset_count} supporting assets are linked to help tell the story."

    summary = f"Auto-generated biography: {event_line} {asset_line}"
    return summary[:1200], "Summary generated from current events and linked assets."


def _should_auto_update_period_summary(period: LifePeriod) -> bool:
    if not period.summary:
        return True
    return period.summary.startswith("Auto-generated summary:") or period.summary.startswith("Auto-generated biography:")


def refresh_period_summary(db: Session, period: Optional[LifePeriod], force: bool = False) -> Optional[str]:
    if not period:
        return None

    if not force and not _should_auto_update_period_summary(period):
        return period.summary

    events = (
        db.query(LifeEvent)
        .filter(LifeEvent.period_id == period.id)
        .order_by(LifeEvent.event_date_sort.is_(None), LifeEvent.event_date_sort.asc(), LifeEvent.created_at.asc())
        .all()
    )
    summary_text, _ = _generate_period_summary(period, events, len(period.assets))
    period.summary = summary_text
    return summary_text


def analyze_period(period: LifePeriod, events: list[LifeEvent], asset_count: int) -> LifePeriodAnalysisResponse:
    period_start_year, period_end_year = _period_bounds_in_years(period)
    event_min_year, event_max_year = _event_year_bounds(events)

    coverage_ok = True
    coverage_gaps: list[str] = []
    if event_min_year is not None and (period_start_year is None or period_start_year > event_min_year):
        coverage_ok = False
        coverage_gaps.append(f"start should be {event_min_year}")
    if event_max_year is not None and (period_end_year is None or period_end_year < event_max_year):
        coverage_ok = False
        coverage_gaps.append(f"end should be {event_max_year}")

    if coverage_ok:
        coverage_reasoning = "Current period dates cover the known event date range."
    elif coverage_gaps:
        coverage_reasoning = "Period date coverage can improve: " + ", ".join(coverage_gaps) + "."
    else:
        coverage_reasoning = "Event dates are too uncertain to assess period coverage."

    rec_start_text, rec_end_text, _, _ = _recommended_period_dates_from_events(events)
    recommended_titles, title_reasoning = _suggest_period_titles(period, events)
    generated_summary, summary_reasoning = _generate_period_summary(period, events, asset_count)

    return LifePeriodAnalysisResponse(
        period_id=period.id,
        event_count=len(events),
        asset_count=asset_count,
        coverage_ok=coverage_ok,
        coverage_reasoning=coverage_reasoning,
        current_title=period.title,
        recommended_titles=recommended_titles,
        title_reasoning=title_reasoning,
        current_start_date_text=period.start_date_text,
        current_end_date_text=period.end_date_text,
        recommended_start_date_text=rec_start_text,
        recommended_end_date_text=rec_end_text,
        generated_summary=generated_summary,
        summary_reasoning=summary_reasoning,
    )


def build_asset_response(asset: Asset) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        period_id=asset.period_id,
        kind=asset.kind,
        title=asset.title,
        legacy_memory_id=asset.legacy_memory_id,
        original_filename=asset.original_filename,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        captured_at=asset.captured_at,
        captured_at_text=asset.captured_at_text,
        gps_latitude=asset.gps_latitude,
        gps_longitude=asset.gps_longitude,
        camera_make=asset.camera_make,
        camera_model=asset.camera_model,
        lens_model=asset.lens_model,
        orientation=asset.orientation,
        image_width=asset.image_width,
        image_height=asset.image_height,
        playback_url=(asset.download_url if (asset.content_type or "").startswith("audio/") else None),
        text_excerpt=asset.text_excerpt,
        notes=asset.notes,
        download_url=asset.download_url,
        linked_event_ids=[link.event_id for link in asset.event_links],
        created_at=asset.created_at,
    )


def ensure_event_asset_link(db: Session, event: LifeEvent, asset: Asset, relation_type: str = "evidence") -> None:
    exists = any(link.asset_id == asset.id for link in event.linked_assets)
    if not exists:
        db.add(EventAsset(event_id=event.id, asset_id=asset.id, relation_type=relation_type[:30]))


def get_or_create_period_for_memory(db: Session, memory: MemoryEntry) -> LifePeriod:
    if memory.date_year:
        title = f"{memory.date_year}"
        slug = f"year-{memory.date_year}"
        start_sort = date(memory.date_year, 1, 1)
        end_sort = date(memory.date_year, 12, 31)
        start_text = str(memory.date_year)
        end_text = str(memory.date_year)
    elif memory.date_decade:
        decade_start = memory.date_decade
        decade_end = memory.date_decade + 9
        title = f"{decade_start}s"
        slug = f"decade-{decade_start}"
        start_sort = date(decade_start, 1, 1)
        end_sort = date(decade_end, 12, 31)
        start_text = str(decade_start)
        end_text = str(decade_end)
    elif memory.estimated_date_sort:
        inferred_year = memory.estimated_date_sort.year
        title = f"{inferred_year}"
        slug = f"year-{inferred_year}"
        start_sort = date(inferred_year, 1, 1)
        end_sort = date(inferred_year, 12, 31)
        start_text = str(inferred_year)
        end_text = str(inferred_year)
    else:
        title = "Undated"
        slug = "undated"
        start_sort = None
        end_sort = None
        start_text = "unknown"
        end_text = "unknown"

    period = db.query(LifePeriod).filter(LifePeriod.slug == slug).first()
    if period:
        return period

    period = LifePeriod(
        title=title,
        slug=unique_period_slug(db, slug),
        start_date_text=start_text,
        end_date_text=end_text,
        start_sort=start_sort,
        end_sort=end_sort,
        summary="Auto-created from existing memories.",
    )
    db.add(period)
    db.flush()
    return period
