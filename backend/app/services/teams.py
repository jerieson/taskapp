"""Teams (admin only)."""

import logging

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.pagination import Page, PaginationParams
from app.models import ProdLog, Team, User
from app.schemas.teams import TeamIn, TeamOut

logger = logging.getLogger("app.teams")


def _name_taken() -> AppError:
    return AppError(
        409,
        "team_name_taken",
        "A team with this name already exists",
        fields={"name": "A team with this name already exists"},
    )


async def _get(db: AsyncSession, team_id: int) -> Team:
    team = await db.get(Team, team_id)
    if team is None:
        raise AppError(404, "not_found", "Team not found")
    return team


async def _ensure_name_free(db: AsyncSession, name: str, exclude_id: int | None = None) -> None:
    cond = func.lower(Team.name) == name.lower()
    if exclude_id is not None:
        cond = cond & (Team.id != exclude_id)
    if await db.scalar(select(exists().where(cond))):
        raise _name_taken()


async def _member_count(db: AsyncSession, team_id: int) -> int:
    return await db.scalar(select(func.count()).where(User.team_id == team_id)) or 0


async def _commit_name(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:  # lost a race on the unique name
        await db.rollback()
        raise _name_taken() from exc


def _out(team: Team, member_count: int) -> TeamOut:
    return TeamOut(
        id=team.id, name=team.name, member_count=member_count, created_at=team.created_at
    )


async def list_teams(db: AsyncSession, params: PaginationParams) -> Page[TeamOut]:
    members = select(func.count()).where(User.team_id == Team.id).correlate(Team).scalar_subquery()
    stmt = select(Team, members.label("member_count")).order_by(func.lower(Team.name), Team.id)
    count = await db.scalar(select(func.count()).select_from(Team)) or 0
    rows = await db.execute(stmt.limit(params.limit).offset(params.offset))
    return Page[TeamOut].build([_out(t, n) for t, n in rows.all()], count, params)


async def create_team(db: AsyncSession, data: TeamIn) -> TeamOut:
    await _ensure_name_free(db, data.name)
    team = Team(name=data.name)
    db.add(team)
    await _commit_name(db)
    await db.refresh(team)
    logger.info("team_created", extra={"fields": {"team_id": team.id}})
    return _out(team, 0)


async def rename_team(db: AsyncSession, team_id: int, data: TeamIn) -> TeamOut:
    team = await _get(db, team_id)
    await _ensure_name_free(db, data.name, exclude_id=team.id)
    team.name = data.name
    await _commit_name(db)
    await db.refresh(team)
    logger.info("team_renamed", extra={"fields": {"team_id": team.id}})
    return _out(team, await _member_count(db, team.id))


async def delete_team(db: AsyncSession, team_id: int) -> None:
    """Blocked while any user or prod log references the team (its invites cascade)."""
    team = await _get(db, team_id)
    has_users = await db.scalar(select(exists().where(User.team_id == team.id)))
    has_logs = await db.scalar(select(exists().where(ProdLog.team_id == team.id)))
    if has_users or has_logs:
        raise AppError(
            409,
            "team_in_use",
            "This team still has users or prod logs and cannot be deleted",
        )
    await db.delete(team)
    try:
        await db.commit()
    except IntegrityError as exc:  # a user or log was added concurrently
        await db.rollback()
        raise AppError(
            409, "team_in_use", "This team still has users or prod logs and cannot be deleted"
        ) from exc
    logger.info("team_deleted", extra={"fields": {"team_id": team_id}})
