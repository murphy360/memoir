"""What the account routes take and return."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.accounts.models import Role


class LoginRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=256)


class Me(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: Role
    is_executor: bool
    must_change_password: bool


class UpdateMe(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


class ChangePassword(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class SessionInfo(BaseModel):
    id: int
    created_at: datetime
    last_seen_at: datetime
    user_agent: str | None
    ip: str | None
    current: bool


class UserOut(Me):
    created_at: datetime


class UpdateUser(BaseModel):
    role: Role | None = None
    is_executor: bool | None = None


class TemporaryPassword(BaseModel):
    password: str = Field(max_length=256)


class CreateInvitation(BaseModel):
    email: EmailStr
    role: Role = Role.CONTRIBUTOR
    is_executor: bool = False


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: Role
    is_executor: bool
    expires_at: datetime
    created_at: datetime


class CreatedInvitation(InvitationOut):
    # Shown once, to the owner who made it. Only its hash is kept.
    link: str


class InvitationPreview(BaseModel):
    email: str
    role: Role
    archive_name: str
    invited_by: str | None


class AcceptInvitation(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(max_length=256)


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    actor_id: int | None
    subject_user_id: int | None
    ip: str | None
    detail: dict
    created_at: datetime
