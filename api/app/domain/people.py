"""People: everyone in the family's life, with or without a login. Each has
a timeline.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import Base, get_session
from app.core.errors import ApiError
from app.dates.store import MANUAL, set_point
from app.domain.common import ArchiveRow, clean, live, scoped, soft_delete
from app.domain.pagination import Page, PageParams, paginate


class Person(ArchiveRow, Base):
    __tablename__ = "people"
    __table_args__ = (
        Index(
            "uq_people_archive_name",
            "archive_id",
            func.lower("name"),
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    birth_text: Mapped[str | None] = mapped_column(String(100))
    birth_start: Mapped[date | None] = mapped_column(Date)
    birth_end: Mapped[date | None] = mapped_column(Date)
    birth_source: Mapped[str | None] = mapped_column(String(16))
    death_text: Mapped[str | None] = mapped_column(String(100))
    death_start: Mapped[date | None] = mapped_column(Date)
    death_end: Mapped[date | None] = mapped_column(Date)
    death_source: Mapped[str | None] = mapped_column(String(16))
    # Named in a story but not yet confirmed by a person (created by extraction).
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    # The person's own login, when they have one.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )


class PersonAlias(Base):
    """Another name for a person ("Mom", "Grandpa Joe"). One alias may name several
    people.
    """

    __tablename__ = "person_aliases"
    __table_args__ = (
        Index(
            "uq_person_aliases_person_alias",
            "person_id",
            func.lower("alias"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(120))


# ---------------------------------------------------------------- schemas


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(None, max_length=80)
    email: str | None = Field(None, max_length=255)
    address: str | None = Field(None, max_length=255)
    notes: str | None = None
    birth_text: str | None = Field(None, max_length=100)
    death_text: str | None = Field(None, max_length=100)
    user_id: int | None = None
    keep_text_only: bool = Field(
        False, description="Save a date Memoir cannot read, as text only"
    )


class PersonPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    phone: str | None = Field(None, max_length=80)
    email: str | None = Field(None, max_length=255)
    address: str | None = Field(None, max_length=255)
    notes: str | None = None
    birth_text: str | None = Field(None, max_length=100)
    death_text: str | None = Field(None, max_length=100)
    user_id: int | None = None
    keep_text_only: bool = Field(
        False, description="Save a date Memoir cannot read, as text only"
    )


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    aliases: list[str] = []
    phone: str | None
    email: str | None
    address: str | None
    notes: str | None
    birth_text: str | None
    birth_start: date | None
    death_text: str | None
    death_start: date | None
    user_id: int | None
    needs_review: bool = False


class AliasIn(BaseModel):
    alias: str = Field(min_length=1, max_length=120)


# ---------------------------------------------------------------- service


def aliases_of(session: Session, person_ids: list[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {pid: [] for pid in person_ids}
    rows = session.scalars(
        select(PersonAlias)
        .where(PersonAlias.person_id.in_(person_ids))
        .order_by(func.lower(PersonAlias.alias))
    )
    for row in rows:
        out[row.person_id].append(row.alias)
    return out


def out(session: Session, people: list[Person]) -> list[PersonOut]:
    names = aliases_of(session, [p.id for p in people])
    return [
        PersonOut.model_validate(p).model_copy(update={"aliases": names[p.id]})
        for p in people
    ]


def by_name(session: Session, user: User, name: str) -> Person | None:
    return session.scalars(
        scoped(Person, user).where(func.lower(Person.name) == name.strip().lower())
    ).first()


def _check_name(session: Session, user: User, name: str, me: int | None) -> str:
    name = clean(name, 120)
    other = by_name(session, user, name or "")
    if not name or (other and other.id != me):
        raise ApiError(409, "name_taken", "Someone already has that name.", "name")
    return name


def _check_user_link(
    session: Session, user: User, user_id: int | None, me: int | None = None
) -> None:
    if user_id is None:
        return
    target = session.get(User, user_id)
    if target is None or target.archive_id != user.archive_id:
        raise ApiError(404, "not_found", "No such user.", "user_id")
    holder = session.scalars(select(Person.id).where(Person.user_id == user_id)).first()
    if holder is not None and holder != me:
        raise ApiError(
            409, "login_taken", "That login already belongs to someone.", "user_id"
        )


TEXT_FIELDS = {"phone": 80, "email": 255, "address": 255, "notes": 10_000}


def create(session: Session, user: User, body: PersonIn) -> Person:
    _check_user_link(session, user, body.user_id)
    person = Person(
        archive_id=user.archive_id,
        name=_check_name(session, user, body.name, None),
        user_id=body.user_id,
        **{f: clean(getattr(body, f), n) for f, n in TEXT_FIELDS.items()},
    )
    for life in ("birth", "death"):
        set_point(
            person, life, getattr(body, f"{life}_text"), MANUAL, body.keep_text_only
        )
    session.add(person)
    session.commit()
    return person


def update(session: Session, user: User, person: Person, body: PersonPatch) -> Person:
    sent = body.model_fields_set
    if "name" in sent and body.name:
        person.name = _check_name(session, user, body.name, person.id)
    if "user_id" in sent:
        _check_user_link(session, user, body.user_id, person.id)
        person.user_id = body.user_id
    for field, limit in TEXT_FIELDS.items():
        if field in sent:
            setattr(person, field, clean(getattr(body, field), limit))
    for life in ("birth", "death"):
        if f"{life}_text" in sent:
            text = getattr(body, f"{life}_text")
            set_point(person, life, text, MANUAL, body.keep_text_only)
    session.commit()
    return person


def add_alias(session: Session, user: User, person: Person, alias: str) -> None:
    alias = clean(alias, 120) or ""
    named = by_name(session, user, alias)
    if named and named.id != person.id:
        raise ApiError(409, "alias_is_a_name", "That is someone else's name.", "alias")
    if named or alias.lower() in [
        a.lower() for a in aliases_of(session, [person.id])[person.id]
    ]:
        return
    session.add(PersonAlias(person_id=person.id, alias=alias))
    session.commit()


def remove_alias(session: Session, person: Person, alias: str) -> None:
    for row in session.scalars(
        select(PersonAlias).where(
            PersonAlias.person_id == person.id,
            func.lower(PersonAlias.alias) == alias.strip().lower(),
        )
    ):
        session.delete(row)
    session.commit()


def resolve(session: Session, user: User, name: str) -> list[Person]:
    """Everyone a name or alias refers to ("the kids" may be several people)."""
    exact = by_name(session, user, name)
    if exact:
        return [exact]
    return list(
        session.scalars(
            scoped(Person, user)
            .join(PersonAlias, PersonAlias.person_id == Person.id)
            .where(func.lower(PersonAlias.alias) == name.strip().lower())
            .order_by(Person.id)
        )
    )


# ---------------------------------------------------------------- router

router = APIRouter(prefix="/api/people", tags=["people"])
reader = require_role(Role.VIEWER)
writer = require_role(Role.CONTRIBUTOR)


@router.get("", response_model=Page[PersonOut])
def list_people(
    q: str | None = Query(None, max_length=120, description="Name or alias contains"),
    page: PageParams = Depends(),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    stmt = scoped(Person, user)
    if q:
        like = f"%{q.strip().lower()}%"
        aliased = select(PersonAlias.person_id).where(
            func.lower(PersonAlias.alias).like(like)
        )
        stmt = stmt.where(func.lower(Person.name).like(like) | Person.id.in_(aliased))
    rows, cursor = paginate(db, stmt, [func.lower(Person.name), Person.id], page)
    return Page(items=out(db, rows), next_cursor=cursor)


@router.post("", response_model=PersonOut, status_code=201)
def create_person(
    body: PersonIn, user: User = Depends(writer), db: Session = Depends(get_session)
):
    return out(db, [create(db, user, body)])[0]


@router.get("/{person_id}", response_model=PersonOut)
def get_person(
    person_id: int, user: User = Depends(reader), db: Session = Depends(get_session)
):
    return out(db, [live(db, Person, person_id, user, "person")])[0]


@router.patch("/{person_id}", response_model=PersonOut)
def update_person(
    person_id: int,
    body: PersonPatch,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    person = live(db, Person, person_id, user, "person")
    return out(db, [update(db, user, person, body)])[0]


@router.post("/{person_id}/aliases", response_model=PersonOut)
def add_person_alias(
    person_id: int,
    body: AliasIn,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    person = live(db, Person, person_id, user, "person")
    add_alias(db, user, person, body.alias)
    return out(db, [person])[0]


@router.delete("/{person_id}/aliases/{alias}", response_model=PersonOut)
def remove_person_alias(
    person_id: int,
    alias: str,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    person = live(db, Person, person_id, user, "person")
    remove_alias(db, person, alias)
    return out(db, [person])[0]


def delete_person(session: Session, person: Person) -> None:
    """Soft-delete a person and their periods (and the periods' epics). Shared events
    stay on everyone else's timeline; the person simply leaves them."""
    from app.domain.periods import soft_delete_periods_of

    soft_delete_periods_of(session, person.id)
    soft_delete(person)
    session.commit()


@router.delete("/{person_id}", status_code=204)
def remove_person(
    person_id: int, user: User = Depends(writer), db: Session = Depends(get_session)
) -> None:
    delete_person(db, live(db, Person, person_id, user, "person"))
