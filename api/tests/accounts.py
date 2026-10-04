"""Helpers for the account tests: make people, sign them in."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Role, User
from app.accounts.owner import create_owner
from app.accounts.passwords import hash_password
from app.archive.models import Archive
from tests.conftest import make_client

PASSWORD = "correct horse battery"


def owner(session: Session, email: str = "owner@example.org") -> User:
    return create_owner(
        session,
        email=email,
        display_name="Owner",
        password=PASSWORD,
        archive_name="The Murphys",
    )


def member(
    session: Session, role: Role, email: str | None = None, executor: bool = False
) -> User:
    archive = session.scalars(select(Archive)).first() or Archive(name="The Murphys")
    session.add(archive)
    session.flush()
    user = User(
        archive_id=archive.id,
        email=email or f"{role.value}@example.org",
        display_name=role.value.title(),
        password_hash=hash_password(PASSWORD),
        role=role,
        is_executor=executor,
    )
    session.add(user)
    session.commit()
    return user


def sign_in(email: str, password: str = PASSWORD, client=None):
    """A client signed in as `email`, sending its CSRF token on every request."""
    c = client or make_client()
    response = c.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    c.headers["X-CSRF-Token"] = c.cookies["memoir_csrf"]
    return c
