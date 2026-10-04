"""What the owner does to other accounts: roles, temporary passwords, removal."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts import audit, sessions
from app.accounts.models import Role, User
from app.accounts.passwords import check_rules, hash_password
from app.core.db import utcnow
from app.core.errors import ApiError


def listing(session: Session, archive_id: int) -> list[User]:
    return list(
        session.scalars(
            select(User)
            .where(User.archive_id == archive_id, User.deleted_at.is_(None))
            .order_by(User.created_at)
        )
    )


def get(session: Session, owner: User, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None or user.archive_id != owner.archive_id or user.deleted_at:
        raise ApiError(404, "not_found", "No such user.")
    return user


def _owners(session: Session, archive_id: int) -> int:
    return session.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.archive_id == archive_id,
            User.role == Role.OWNER,
            User.deleted_at.is_(None),
        )
    )


def _keep_an_owner(session: Session, user: User) -> None:
    if user.role == Role.OWNER and _owners(session, user.archive_id) <= 1:
        raise ApiError(
            409, "last_owner", "The archive must keep at least one owner.", "role"
        )


def update(
    session: Session, owner: User, user: User, role: Role | None, executor: bool | None
) -> User:
    if role is not None and role != user.role:
        if role != Role.OWNER:
            _keep_an_owner(session, user)
        audit.record(
            session,
            "role.changed",
            archive_id=owner.archive_id,
            actor_id=owner.id,
            subject_user_id=user.id,
            old=user.role,
            new=role.value,
        )
        user.role = role
    if executor is not None and executor != user.is_executor:
        audit.record(
            session,
            "executor.granted" if executor else "executor.revoked",
            archive_id=owner.archive_id,
            actor_id=owner.id,
            subject_user_id=user.id,
        )
        user.is_executor = executor
    session.commit()
    return user


def set_temporary_password(
    session: Session, owner: User, user: User, password: str
) -> None:
    """The owner's reset: the user must pick their own at next sign-in."""
    check_rules(password, user.email)
    user.password_hash = hash_password(password)
    user.must_change_password = True
    audit.record(
        session,
        "password.reset",
        archive_id=owner.archive_id,
        actor_id=owner.id,
        subject_user_id=user.id,
    )
    session.commit()
    sessions.revoke_all(session, user.id)


def remove(session: Session, owner: User, user: User) -> None:
    if user.id == owner.id:
        raise ApiError(409, "cannot_remove_self", "You cannot remove yourself.")
    _keep_an_owner(session, user)
    user.deleted_at = utcnow()
    audit.record(
        session,
        "user.removed",
        archive_id=owner.archive_id,
        actor_id=owner.id,
        subject_user_id=user.id,
    )
    session.commit()
    sessions.revoke_all(session, user.id)
