"""Admin overview: headline counts and AI usage."""

from pydantic import BaseModel

from app.schemas.prod_logs import UserRef

AI_USAGE_DAYS = 30


class UserCounts(BaseModel):
    active: int
    inactive: int
    admins: int
    """Active admins."""
    managers: int
    """Active managers."""
    devs: int
    """Active devs."""


class AdminOverview(BaseModel):
    users: UserCounts
    teams: int
    pending_invites: int
    """Not accepted and not expired."""


class AIUsageRow(BaseModel):
    user: UserRef
    is_active: bool
    requests: int
    failed: int
    input_tokens: int
    output_tokens: int
