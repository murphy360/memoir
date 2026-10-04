"""Extraction: what a transcript says, by structured output (requirements 6.3).

One call yields the date, the storyteller, the people and places named, a title, a
description and the tone. Names resolve through the directory and its aliases; an alias
for several people names them all. A name nobody has yet becomes a person (or place)
marked for review, never a silent guess. What the archive already holds wins: a typed
date, title or description is not replaced, and existing mentions are kept.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.ai import registry
from app.ai.costs import recorded
from app.ai.provider import ProviderError
from app.analysis.common import acting_user, ai_for, load
from app.core.db import utcnow
from app.dates.store import set_by_job
from app.domain import people as people_mod
from app.domain.common import Precision, scoped
from app.domain.memories import Memory, MemoryMention, MemoryPlace, join_event
from app.domain.people import Person
from app.domain.places import Place
from app.jobs import queue
from app.jobs.registry import JobContext, PermanentError, handler
from app.placement.service import autofile

PROMPT_VERSION = "extract-1"
TONES = ("positive", "negative", "reflective", "neutral", "mixed")
EFFECTS = (
    "married",
    "deployed",
    "moved",
    "born",
    "died",
    "divorced",
    "started_college",
    "other",
)

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "4 to 10 words naming what happened",
        },
        "description": {
            "type": "string",
            "description": "one paragraph, third person, only what the transcript says",
        },
        "date_text": {
            "type": "string",
            "description": "when it happened, as a person would say it (summer 1968); "
            "empty if the transcript does not say",
        },
        "date_precision": {"type": "string", "enum": [p.value for p in Precision]},
        "storyteller_name": {
            "type": "string",
            "description": "the speaker's own name if they say it; empty otherwise",
        },
        "people": {
            "type": "array",
            "items": {"type": "string"},
            "description": "everyone else named, by name or family title "
            "(Mom, Uncle Jim)",
        },
        "places": {"type": "array", "items": {"type": "string"}},
        "tone": {"type": "string", "enum": list(TONES)},
        "relationship_effects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(EFFECTS)},
                    "people": {"type": "array", "items": {"type": "string"}},
                    "date_text": {"type": "string"},
                },
                "required": ["kind", "people"],
            },
        },
    },
    "required": [
        "title",
        "description",
        "date_text",
        "date_precision",
        "people",
        "places",
        "tone",
    ],
}


def prompt(transcript: str, known: list[str]) -> str:
    names = ", ".join(known[:200]) or "none yet"
    return (
        "You read the transcript of a family memory and record what it says. Use only "
        "what the transcript says: never invent a name, a place or a date. Spell names "
        "the way the family already does when the transcript means the same person.\n"
        f"People the family already knows: {names}.\n\nTranscript:\n{transcript}"
    )


def clean_names(names, limit: int = 120) -> list[str]:
    seen, out = set(), []
    for name in names or []:
        name = " ".join(str(name).split())[:limit]
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            out.append(name)
    return out


def known_names(session: Session, user: User) -> list[str]:
    return list(
        session.scalars(scoped(Person, user).with_only_columns(Person.name).limit(200))
    )


def resolve_people(
    session: Session, user: User, names: list[str], created: list
) -> list[int]:
    """Ids for the names: everyone an alias names, or a new person to review."""
    ids: list[int] = []
    for name in names:
        found = people_mod.resolve(session, user, name)
        if not found:
            found = [Person(archive_id=user.archive_id, name=name, needs_review=True)]
            session.add(found[0])
            session.flush()
            created.append(name)
        ids += [p.id for p in found if p.id not in ids]
    return ids


def resolve_places(
    session: Session, user: User, names: list[str], created: list
) -> list[int]:
    ids: list[int] = []
    for name in clean_names(names, 200):
        place = session.scalars(
            scoped(Place, user).where(func.lower(Place.name) == name.lower())
        ).first()
        if place is None:
            place = Place(archive_id=user.archive_id, name=name, needs_review=True)
            session.add(place)
            session.flush()
            created.append(name)
        if place.id not in ids:
            ids.append(place.id)
    return ids


def _storyteller(session: Session, user: User, memory: Memory, name: str, report: dict):
    if memory.storyteller_id or not name:
        return
    found = people_mod.resolve(session, user, name)
    if len(found) > 1:
        report["ambiguous_storyteller"] = name
        return
    if found:
        memory.storyteller_id = found[0].id
    else:
        memory.storyteller_id = resolve_people(
            session, user, [name], report["created_people"]
        )[0]


def _link(session: Session, model, memory_id: int, column: str, ids: list[int]) -> None:
    have = set(
        session.scalars(
            select(getattr(model, column)).where(model.memory_id == memory_id)
        )
    )
    for i in ids:
        if i not in have:
            session.add(model(memory_id=memory_id, **{column: i}))
    session.flush()


def apply(session: Session, user: User, memory: Memory, data: dict, model: str) -> dict:
    report = {"created_people": [], "created_places": [], "model": model}
    _storyteller(
        session, user, memory, (data.get("storyteller_name") or "").strip(), report
    )
    teller = (
        session.get(Person, memory.storyteller_id) if memory.storyteller_id else None
    )
    mentioned = [
        n
        for n in clean_names(data.get("people"))
        if not teller or n.casefold() != teller.name.casefold()
    ]
    _link(
        session,
        MemoryMention,
        memory.id,
        "person_id",
        resolve_people(session, user, mentioned, report["created_people"]),
    )
    _link(
        session,
        MemoryPlace,
        memory.id,
        "place_id",
        resolve_places(session, user, data.get("places"), report["created_places"]),
    )
    if data.get("date_text"):
        set_by_job(memory, "date", data["date_text"], "transcript")
    if not memory.title and data.get("title"):
        memory.title = " ".join(data["title"].split())[:180]
    if not memory.description and data.get("description"):
        memory.description = data["description"].strip()[:20_000]
    if data.get("tone") in TONES:
        memory.tone = data["tone"]
    report["relationship_effects"] = data.get("relationship_effects") or []
    report["prompt_version"], report["at"] = PROMPT_VERSION, utcnow().isoformat()
    memory.extracted = report
    join_event(session, memory)
    return report


@handler("analysis.extract")
def extract(ctx: JobContext, payload: dict) -> dict:
    memory = load(ctx.session, payload["memory_id"])
    if not (memory.transcript or "").strip():
        memory.extraction_state = "needs_details"
        ctx.session.commit()
        return {"state": "needs_details", "reason": "no transcript"}
    provider, settings = ai_for(ctx.session, memory, "ai_extraction", "extract")
    if provider is None:
        memory.extraction_state = "ai_off"
        ctx.session.commit()
        return {"state": "ai_off"}
    user = acting_user(ctx.session, memory)
    model = registry.model_for(settings, "extract", provider.name)
    text = prompt(memory.transcript, known_names(ctx.session, user))
    try:
        answer = recorded(
            ctx.session,
            provider,
            lambda: provider.structured(text, SCHEMA, model),
            task="extract",
            model=model,
            prompt_version=PROMPT_VERSION,
            archive_id=memory.archive_id,
            memory_id=memory.id,
        )
    except ProviderError as exc:
        if ctx.last_attempt or not exc.retryable:
            memory.extraction_state = "needs_details"
            memory.analysis_error = str(exc)[:500]
            ctx.session.commit()
        if not exc.retryable:
            raise PermanentError(str(exc)) from exc
        raise
    report = apply(ctx.session, user, memory, answer.data, answer.model)
    memory.extraction_state = "done"
    ctx.session.commit()
    # Now that the date is known, a quick memory is filed where it belongs (once),
    # and the interviewer asks about it.
    autofile(ctx.session, memory)
    queue.enqueue(
        ctx.session,
        "questions.generate",
        {"memory_id": memory.id},
        idempotency_key=f"questions:{memory.id}",
    )
    return {"state": "done", "created_people": report["created_people"]}
