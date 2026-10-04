"""Write an entry to the audit log. The caller commits."""

from sqlalchemy.orm import Session

from app.accounts.models import AuditEvent


def record(
    session: Session,
    kind: str,
    *,
    archive_id: int | None,
    actor_id: int | None = None,
    subject_user_id: int | None = None,
    ip: str | None = None,
    **detail,
) -> None:
    session.add(
        AuditEvent(
            kind=kind,
            archive_id=archive_id,
            actor_id=actor_id,
            subject_user_id=subject_user_id,
            ip=ip,
            detail=detail,
        )
    )
