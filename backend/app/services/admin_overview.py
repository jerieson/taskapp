"""Admin overview numbers, all computed in SQL."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, PaginationParams
from app.db.base import utcnow
from app.models import AIRequest, Invite, Role, Team, User
from app.schemas.admin_overview import AI_USAGE_DAYS, AdminOverview, AIUsageRow, UserCounts
from app.schemas.prod_logs import UserRef
from app.services.invites import is_pending


async def overview(db: AsyncSession) -> AdminOverview:
    active = User.is_active
    users = (
        await db.execute(
            select(
                func.count().filter(active),
                func.count().filter(~active),
                func.count().filter(active, User.role == Role.ADMIN),
                func.count().filter(active, User.role == Role.MANAGER),
                func.count().filter(active, User.role == Role.DEV),
            )
        )
    ).one()
    teams = await db.scalar(select(func.count()).select_from(Team)) or 0
    pending = await db.scalar(select(func.count()).select_from(Invite).where(is_pending())) or 0
    return AdminOverview(
        users=UserCounts(
            active=users[0], inactive=users[1], admins=users[2], managers=users[3], devs=users[4]
        ),
        teams=teams,
        pending_invites=pending,
    )


async def ai_usage(db: AsyncSession, params: PaginationParams) -> Page[AIUsageRow]:
    """AI requests per user over the last 30 days, most requests first. Only users with
    at least one request are listed."""
    since = utcnow() - timedelta(days=AI_USAGE_DAYS)
    requests = func.count().label("requests")
    stmt = (
        select(
            User,
            requests,
            func.count().filter(~AIRequest.success),
            func.coalesce(func.sum(AIRequest.input_tokens), 0),
            func.coalesce(func.sum(AIRequest.output_tokens), 0),
        )
        .join(AIRequest, AIRequest.user_id == User.id)
        .where(AIRequest.created_at >= since)
        .group_by(User.id)
    )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.execute(
        stmt.order_by(requests.desc(), func.lower(User.username))
        .limit(params.limit)
        .offset(params.offset)
    )
    items = [
        AIUsageRow(
            user=UserRef.model_validate(user),
            is_active=user.is_active,
            requests=count,
            failed=failed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        for user, count, failed, input_tokens, output_tokens in rows.all()
    ]
    return Page[AIUsageRow].build(items, total, params)
