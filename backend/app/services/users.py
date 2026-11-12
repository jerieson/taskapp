"""User lookups shared by several features."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Team, User
from app.schemas.auth import MeOut, TeamRef


async def to_me(db: AsyncSession, user: User) -> MeOut:
    team = await db.get(Team, user.team_id) if user.team_id is not None else None
    return MeOut(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        team=TeamRef.model_validate(team) if team else None,
        has_password=user.password_hash is not None,
        google_linked=user.google_sub is not None,
        created_at=user.created_at,
    )
