"""The owner's view of the archive's accounts, and the audit log."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts import users
from app.accounts.deps import require_role
from app.accounts.models import AuditEvent, Role, User
from app.accounts.schemas import AuditEntry, TemporaryPassword, UpdateUser, UserOut
from app.core.db import get_session
from app.core.errors import ErrorResponse

router = APIRouter(tags=["users"])
owner_only = require_role(Role.OWNER)
REFUSED = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


@router.get("/api/users", response_model=list[UserOut], responses=REFUSED)
def list_users(
    owner: User = Depends(owner_only), db: Session = Depends(get_session)
) -> list[User]:
    return users.listing(db, owner.archive_id)


@router.patch("/api/users/{user_id}", response_model=UserOut, responses=REFUSED)
def update_user(
    user_id: int,
    body: UpdateUser,
    owner: User = Depends(owner_only),
    db: Session = Depends(get_session),
) -> User:
    target = users.get(db, owner, user_id)
    return users.update(db, owner, target, body.role, body.is_executor)


@router.post(
    "/api/users/{user_id}/temporary-password", status_code=204, responses=REFUSED
)
def temporary_password(
    user_id: int,
    body: TemporaryPassword,
    owner: User = Depends(owner_only),
    db: Session = Depends(get_session),
) -> None:
    users.set_temporary_password(
        db, owner, users.get(db, owner, user_id), body.password
    )


@router.delete("/api/users/{user_id}", status_code=204, responses=REFUSED)
def remove_user(
    user_id: int, owner: User = Depends(owner_only), db: Session = Depends(get_session)
) -> None:
    users.remove(db, owner, users.get(db, owner, user_id))


@router.get("/api/audit", response_model=list[AuditEntry], responses=REFUSED)
def audit_log(
    limit: int = Query(100, ge=1, le=500),
    owner: User = Depends(owner_only),
    db: Session = Depends(get_session),
) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.archive_id == owner.archive_id)
            .order_by(AuditEvent.id.desc())
            .limit(limit)
        )
    )
