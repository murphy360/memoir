"""Follow-up questions from a memory's transcript (requirements 6.5 and 16).

Two or three questions about feeling, significance, people and what is missing, from
the transcript with the storyteller, date, people and places as context. Each is scoped
to the memory's event, its period, a person it names, or general, and is for the
memory's storyteller. A question already asked (in any state) is not asked again.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import registry
from app.ai.costs import recorded
from app.ai.provider import ProviderError
from app.analysis.common import acting_user, ai_for, load
from app.domain import people as people_mod
from app.domain.events import Event
from app.domain.memories import Memory, MemoryMention, MemoryPlace
from app.domain.participants import Participant
from app.domain.people import Person
from app.domain.periods import Period
from app.domain.places import Place
from app.domain.questions import Question, QuestionIn, Scope, Status, add
from app.jobs.registry import JobContext, PermanentError, handler
from app.placement.service import storyteller_of

PROMPT_VERSION = "questions-1"
MOST = 3
MAX_WORDS = 25
SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "one short open question, at most 20 words",
                    },
                    "about": {
                        "type": "string",
                        "enum": ["event", "period", "person", "general"],
                        "description": "event: this moment; period: that time of "
                        "life; person: someone named; general: anything else",
                    },
                    "person": {
                        "type": "string",
                        "description": "the person it is about, as the transcript "
                        "names them; empty unless about is person",
                    },
                },
                "required": ["text", "about"],
            },
        }
    },
    "required": ["questions"],
}

RULES = (
    "You are an oral historian listening to a family member tell a story. Ask two or "
    "three follow-up questions about what was just said. Rules:\n"
    "- One question each, short, in plain words, as you would say it aloud.\n"
    "- Ask about what is missing: who else was there, how it felt, why it mattered, "
    "what happened next, a detail they mentioned but did not explain.\n"
    "- Never leading: do not suggest an answer or assume a feeling.\n"
    "- Never correct the storyteller or point out a contradiction.\n"
    "- No yes-or-no questions. Do not repeat a question already waiting.\n"
    "- You may start by echoing what they said (You said your brother drove. Which "
    "brother?)."
)


def _names(session: Session, model, link, column, memory_id: int) -> list[str]:
    return list(
        session.scalars(
            select(model.name)
            .join(link, getattr(link, column) == model.id)
            .where(link.memory_id == memory_id)
        )
    )


def _waiting(session: Session, memory: Memory) -> list[str]:
    return list(
        session.scalars(
            select(Question.text)
            .where(
                Question.archive_id == memory.archive_id,
                Question.status == Status.PENDING,
                Question.deleted_at.is_(None),
            )
            .order_by(Question.created_at.desc())
            .limit(40)
        )
    )


def prompt(session: Session, memory: Memory, teller: Person | None) -> str:
    event = session.get(Event, memory.event_id) if memory.event_id else None
    named = _names(session, Person, MemoryMention, "person_id", memory.id)
    places = _names(session, Place, MemoryPlace, "place_id", memory.id)
    known = [
        ("Storyteller", teller.name if teller else "unknown"),
        ("When", memory.date_text or (event and event.date_text) or "not said"),
        ("People named", ", ".join(named) or "none"),
        ("Places", ", ".join(places) or "none"),
        ("Event", event.title if event else "not placed yet"),
    ]
    lines = "\n".join(f"{k}: {v}" for k, v in known)
    waiting = "\n".join(f"- {t}" for t in _waiting(session, memory)) or "none"
    return (
        f"{RULES}\n\n{lines}\n\nQuestions already waiting:\n{waiting}\n\n"
        f"Transcript:\n{(memory.transcript or '')[:20_000]}"
    )


def tidy(text: str) -> str | None:
    """One short question, or None. Past a second question mark is cut off."""
    text = " ".join(str(text or "").split())
    if "?" in text:
        text = text[: text.index("?") + 1]
    elif text and text[-1] not in ".!":
        text += "?"
    if len(text) < 3 or len(text) > 200 or len(text.split()) > MAX_WORDS:
        return None
    return text


def _period_of(session: Session, event_id: int | None, person_id: int | None):
    if not (event_id and person_id):
        return None
    return session.scalars(
        select(Participant.period_id).where(
            Participant.event_id == event_id, Participant.person_id == person_id
        )
    ).first()


def scope_for(session, user, memory: Memory, item: dict, teller_id) -> QuestionIn:
    """Where the question belongs; general when its target is not known."""
    about, text = item.get("about"), item["text"]
    if about == "event" and memory.event_id:
        return QuestionIn(text=text, scope=Scope.EVENT, event_id=memory.event_id)
    period_id = _period_of(session, memory.event_id, teller_id)
    if about == "period" and period_id and session.get(Period, period_id):
        return QuestionIn(text=text, scope=Scope.PERIOD, period_id=period_id)
    if about == "person" and (item.get("person") or "").strip():
        mentioned = set(
            session.scalars(
                select(MemoryMention.person_id).where(
                    MemoryMention.memory_id == memory.id
                )
            )
        )
        found = [
            p
            for p in people_mod.resolve(session, user, item["person"].strip())
            if p.id in mentioned
        ]
        if len(found) == 1:
            return QuestionIn(text=text, scope=Scope.PERSON, person_id=found[0].id)
    return QuestionIn(text=text)


def write(session: Session, memory: Memory, data: dict) -> list[int]:
    """Store up to three questions from the answer; returns the ids of new ones."""
    user = acting_user(session, memory)
    teller_id = storyteller_of(session, memory)
    made: list[int] = []
    for item in (data.get("questions") or [])[:MOST]:
        text = tidy(item.get("text") if isinstance(item, dict) else None)
        if text is None:
            continue
        body = scope_for(session, user, memory, {**item, "text": text}, teller_id)
        question = add(session, user, body, memory.id, teller_id, machine=True)
        if question is not None and question.source_memory_id == memory.id:
            made.append(question.id)
    return made


def _give_up(ctx: JobContext, memory: Memory, exc: ProviderError) -> bool:
    """Record a failure that will not be retried; True when retrying cannot help."""
    if ctx.last_attempt or not exc.retryable:
        memory.questions_state = "failed"
        ctx.session.commit()
    return not exc.retryable


@handler("questions.generate")
def generate(ctx: JobContext, payload: dict) -> dict:
    memory = load(ctx.session, payload["memory_id"])
    if not (memory.transcript or "").strip():
        memory.questions_state = "done"
        ctx.session.commit()
        return {"state": "done", "made": 0, "reason": "no transcript"}
    provider, settings = ai_for(ctx.session, memory, "ai_questions")
    if provider is None:
        memory.questions_state = "ai_off"
        ctx.session.commit()
        return {"state": "ai_off"}
    teller_id = storyteller_of(ctx.session, memory)
    teller = ctx.session.get(Person, teller_id) if teller_id else None
    model = registry.model_for(settings, "questions")
    text = prompt(ctx.session, memory, teller)
    try:
        answer = recorded(
            ctx.session,
            provider,
            lambda: provider.structured(text, SCHEMA, model),
            task="questions",
            model=model,
            prompt_version=PROMPT_VERSION,
            archive_id=memory.archive_id,
            memory_id=memory.id,
        )
    except ProviderError as exc:
        if _give_up(ctx, memory, exc):
            raise PermanentError(str(exc)) from exc
        raise
    made = write(ctx.session, memory, answer.data)
    memory.questions_state = "done"
    ctx.session.commit()
    return {"state": "done", "made": len(made)}
