"""Connected agents, for the profile page: who may act as you, and Disconnect."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.accounts import audit
from app.accounts.deps import Signed, signed_in
from app.agents import grants
from app.core.db import get_session
from app.core.errors import ErrorResponse

router = APIRouter(prefix="/api/me/agents", tags=["profile"])
REFUSED = {401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


class ConnectedAgent(BaseModel):
    id: int
    name: str
    connected_at: datetime
    last_used_at: datetime | None


@router.get("", response_model=list[ConnectedAgent], responses=REFUSED)
def my_agents(
    signed: Signed = Depends(signed_in), db: Session = Depends(get_session)
) -> list[ConnectedAgent]:
    """The agents that may act as you, most recently used first."""
    return [
        ConnectedAgent(
            id=grant.id,
            name=client.client_name,
            connected_at=grant.created_at,
            last_used_at=grant.last_used_at,
        )
        for grant, client in grants.connected(db, signed.user)
    ]


@router.delete("/{agent_id}", status_code=204, responses=REFUSED)
def disconnect(
    agent_id: int,
    signed: Signed = Depends(signed_in),
    db: Session = Depends(get_session),
) -> None:
    """End the connection: the agent's next call is refused."""
    audit.record(
        db,
        "agent.disconnected",
        archive_id=signed.user.archive_id,
        actor_id=signed.user.id,
        grant=agent_id,
    )
    grants.disconnect(db, signed.user, agent_id)
