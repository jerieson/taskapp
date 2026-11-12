from datetime import datetime

from pydantic import BaseModel

from app.core.pagination import PaginationParams
from app.models import Role
from app.schemas.auth import TeamRef


class AdminUserOut(BaseModel):
    id: int
    username: str
    email: str
    role: Role
    team: TeamRef | None
    is_active: bool
    has_password: bool
    google_linked: bool
    created_at: datetime


class AdminUserUpdate(BaseModel):
    """Change role and/or team. Admins have no team; every other role needs one.

    Omitted fields keep their current value. Making a user admin clears their team.
    """

    role: Role | None = None
    team_id: int | None = None


class AdminUserQuery(PaginationParams):
    """Pagination plus optional filters for the admin user list."""

    team_id: int | None = None
    role: Role | None = None
    is_active: bool | None = None
