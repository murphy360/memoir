"""Invitations: the owner makes and revokes them; anyone with a link may accept once."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.accounts import invitations
from app.accounts.deps import client_ip, require_role, set_session_cookies
from app.accounts.models import Role, User
from app.accounts.schemas import (
    AcceptInvitation,
    CreatedInvitation,
    CreateInvitation,
    InvitationOut,
    InvitationPreview,
    Me,
)
from app.core.db import get_session
from app.core.errors import ErrorResponse
from app.core.settings import Settings, get_settings

router = APIRouter(prefix="/api/invitations", tags=["invitations"])
owner_only = require_role(Role.OWNER)
REFUSED = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    410: {"model": ErrorResponse},
}


@router.get("", response_model=list[InvitationOut], responses=REFUSED)
def pending_invitations(
    owner: User = Depends(owner_only), db: Session = Depends(get_session)
):
    return invitations.pending(db, owner.archive_id)


@router.post("", response_model=CreatedInvitation, status_code=201, responses=REFUSED)
def invite(
    body: CreateInvitation,
    owner: User = Depends(owner_only),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CreatedInvitation:
    inv, link = invitations.create(
        db, owner, body.email, body.role, body.is_executor, settings
    )
    return CreatedInvitation(
        **InvitationOut.model_validate(inv).model_dump(), link=link
    )


@router.delete("/{invitation_id}", status_code=204, responses=REFUSED)
def revoke_invitation(
    invitation_id: int,
    owner: User = Depends(owner_only),
    db: Session = Depends(get_session),
) -> None:
    invitations.revoke(db, owner, invitation_id)


@router.get("/accept/{token}", response_model=InvitationPreview, responses=REFUSED)
def preview_invitation(token: str, db: Session = Depends(get_session)) -> dict:
    return invitations.preview(db, token)


@router.post("/accept/{token}", response_model=Me, responses=REFUSED)
def accept_invitation(
    token: str,
    body: AcceptInvitation,
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Me:
    user, row, raw = invitations.accept(
        db,
        token,
        body.display_name,
        body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookies(response, raw, row.csrf_token, settings)
    return Me.model_validate(user)
