import json
from typing import Optional

from sqlalchemy.orm import Session

from app.models import MemoryEntry, MemoryPerson, MemoryPlace, Person, PersonAlias, Place
from app.schemas import DirectoryEntryResponse
from app.services.periods import normalize_directory_name


def get_or_create_person(db: Session, raw_name: Optional[str]) -> Optional[Person]:
    name = normalize_directory_name(raw_name)
    if not name:
        return None

    for person in db.query(Person).all():
        if person.name.casefold() == name.casefold():
            if person.name != name:
                person.name = name
            return person

    alias_row = (
        db.query(PersonAlias)
        .filter(PersonAlias.alias.ilike(name))
        .first()
    )
    if alias_row:
        return alias_row.person

    person = Person(name=name)
    db.add(person)
    db.flush()
    return person


def expand_person_names(db: Session, raw_name: Optional[str]) -> list[Person]:
    name = normalize_directory_name(raw_name)
    if not name:
        return []

    for person in db.query(Person).all():
        if person.name.casefold() == name.casefold():
            return [person]

    alias_rows = db.query(PersonAlias).filter(PersonAlias.alias.ilike(name)).all()
    if alias_rows:
        seen: set[int] = set()
        resolved: list[Person] = []
        for row in alias_rows:
            if row.person_id not in seen:
                seen.add(row.person_id)
                resolved.append(row.person)
        return resolved

    person = Person(name=name)
    db.add(person)
    db.flush()
    return [person]


def get_or_create_place(db: Session, raw_name: Optional[str]) -> Optional[Place]:
    name = normalize_directory_name(raw_name)
    if not name:
        return None

    for place in db.query(Place).all():
        if place.name.casefold() == name.casefold():
            if place.name != name:
                place.name = name
            return place

    place = Place(name=name)
    db.add(place)
    db.flush()
    return place


def sync_memory_people(db: Session, memory: MemoryEntry, names: list[str]) -> None:
    ordered_people: list[Person] = []
    seen_keys: set[str] = set()

    for raw_name in names:
        for person in expand_person_names(db, raw_name):
            key = person.name.casefold()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            ordered_people.append(person)

    existing_links = {link.person_id: link for link in memory.people_links}
    desired_ids = {person.id for person in ordered_people}

    for link in list(memory.people_links):
        if link.person_id not in desired_ids:
            memory.people_links.remove(link)
            db.delete(link)

    for person in ordered_people:
        if person.id not in existing_links:
            memory.people_links.append(MemoryPerson(person_id=person.id, role="mentioned"))

    memory.people_json = json.dumps([person.name for person in ordered_people])


def sync_memory_places(db: Session, memory: MemoryEntry, names: list[str]) -> None:
    ordered_places: list[Place] = []
    seen_keys: set[str] = set()

    for raw_name in names:
        place = get_or_create_place(db, raw_name)
        if not place:
            continue
        key = place.name.casefold()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        ordered_places.append(place)

    existing_links = {link.place_id: link for link in memory.place_links}
    desired_ids = {place.id for place in ordered_places}

    for link in list(memory.place_links):
        if link.place_id not in desired_ids:
            memory.place_links.remove(link)
            db.delete(link)

    for place in ordered_places:
        if place.id not in existing_links:
            memory.place_links.append(MemoryPlace(place_id=place.id))

    memory.locations_json = json.dumps([place.name for place in ordered_places])


def assign_recorder_person(db: Session, memory: MemoryEntry, raw_name: Optional[str]) -> None:
    person = get_or_create_person(db, raw_name)
    if not person:
        memory.recorder_person = None
        memory.recorder_person_id = None
        memory.recorder_name = None
        return

    memory.recorder_person = person
    memory.recorder_person_id = person.id
    memory.recorder_name = person.name


def build_directory_response(
    name: str,
    item_id: int,
    memory_count: int,
    aliases: Optional[list[str]] = None,
) -> DirectoryEntryResponse:
    return DirectoryEntryResponse(
        id=item_id,
        name=name,
        memory_count=memory_count,
        aliases=aliases or [],
    )


def list_people_directory(db: Session) -> list[DirectoryEntryResponse]:
    memories = db.query(MemoryEntry).all()
    counts: dict[int, set[int]] = {}

    for memory in memories:
        if memory.recorder_person_id is not None:
            counts.setdefault(memory.recorder_person_id, set()).add(memory.id)
        for link in memory.people_links:
            counts.setdefault(link.person_id, set()).add(memory.id)

    people = db.query(Person).order_by(Person.name.asc()).all()
    return [
        build_directory_response(
            person.name,
            person.id,
            len(counts.get(person.id, set())),
            [alias.alias for alias in person.aliases],
        )
        for person in people
    ]


def list_places_directory(db: Session) -> list[DirectoryEntryResponse]:
    counts: dict[int, set[int]] = {}

    for memory in db.query(MemoryEntry).all():
        for link in memory.place_links:
            counts.setdefault(link.place_id, set()).add(memory.id)

    places = db.query(Place).order_by(Place.name.asc()).all()
    return [
        build_directory_response(place.name, place.id, len(counts.get(place.id, set())))
        for place in places
    ]


def update_memory_json_from_links(memory: MemoryEntry) -> None:
    memory.people_json = json.dumps(memory.referenced_people)
    memory.locations_json = json.dumps(memory.referenced_locations)
