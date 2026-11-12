from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from app.models import Role
from app.schemas.auth import Email, NewPassword, Username


class InviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"


class InviteCreate(BaseModel):
    email: Email
    role: Literal[Role.MANAGER, Role.DEV]
    team_id: int


class InviteOut(BaseModel):
    id: int
    email: str
    role: Role
    team_id: int
    status: InviteStatus
    expires_at: datetime
    accepted_at: datetime | None
    created_by: int
    created_at: datetime


class InviteCreated(InviteOut):
    invite_url: str
    """Shown only once: the database stores only a hash of the token."""


class InvitePublicOut(BaseModel):
    """What the invite page shows before acceptance."""

    email: str
    role: Role
    team_name: str
    expires_at: datetime


class InviteAcceptIn(BaseModel):
    username: Username
    password: NewPassword
