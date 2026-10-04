"""The first account. Created once, from the command line; there is no sign-up."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts import audit
from app.accounts.models import Role, User
from app.accounts.passwords import check_rules, hash_password
from app.archive.models import Archive


class OwnerExists(Exception):
    pass


def create_owner(
    session: Session, *, email: str, display_name: str, password: str, archive_name: str
) -> User:
    """Create the archive and its owner. Refuses when any owner already exists."""
    if session.scalars(select(User).where(User.role == Role.OWNER)).first():
        raise OwnerExists("An owner already exists. Invite people from the app.")
    check_rules(password, email)
    archive = session.scalars(select(Archive)).first() or Archive(name=archive_name)
    session.add(archive)
    session.flush()
    user = User(
        archive_id=archive.id,
        email=email.strip(),
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        role=Role.OWNER,
        is_executor=False,
    )
    session.add(user)
    session.flush()
    audit.record(
        session, "owner.created", archive_id=archive.id, subject_user_id=user.id
    )
    session.commit()
    return user
