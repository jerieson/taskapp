"""AI team summary: a markdown narrative of a team's work over a period.

Access is checked before anything is loaded (managers: own team, admins: any team,
devs: never). Every figure is computed in SQL from the team snapshot on each log
(`prod_logs.team_id`) and handed to the model, which writes prose only. Log remarks are
sent most recent first, cut to AI_SUMMARY_CHAR_BUDGET characters.

Summaries are saved in `ai_summaries`; asking again for the same team and period
returns the newest saved one without calling the AI, unless `regenerate` is set.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.client import AIClient
from app.ai.errors import AIOutputError
from app.ai.prompts.team_summary import SYSTEM, build_prompt, to_json
from app.core.config import Settings
from app.core.errors import AppError
from app.core.pagination import Page
from app.models import Activity, AISummary, DeviationReason, ProdLog, Project, Team, User
from app.models.enums import AIFeature
from app.schemas.ai import (
    TeamSummaryOut,
    TeamSummaryQuery,
    TeamSummaryRequest,
    TeamSummaryResult,
    TeamSummaryStats,
)
from app.schemas.dashboard import DateRangeQuery
from app.schemas.prod_logs import UserRef
from app.services import dashboard
from app.services.prod_logs import check_team_access

ZERO = Decimal("0.00")
TOP_ITEMS = 10
"""Projects, categories and activities listed in the prompt (most hours first)."""
MAX_REMARK_CHARS = 1000
"""One row's remarks are cut to this before the budget applies."""
MAX_SUMMARY_CHARS = 20000


# ---------------------------------------------------------------- figures (SQL)


def _period(team_id: int, start: date, end: date) -> Any:
    return and_(ProdLog.team_id == team_id, ProdLog.log_date.between(start, end))


def _sum(column: Any, *conditions: Any) -> Any:
    value = case((and_(*conditions), column), else_=None) if conditions else column
    return func.coalesce(func.sum(value), ZERO)


def _aggregates() -> list[Any]:
    return [
        _sum(ProdLog.hours_spent),
        _sum(ProdLog.planned_hours),
        _sum(ProdLog.hours_spent, ProdLog.is_planned.is_(False)),
        func.count(ProdLog.id),
        func.count(ProdLog.deviation_reason_id),
    ]


async def team_stats(db: AsyncSession, team_id: int, start: date, end: date) -> TeamSummaryStats:
    row = (
        await db.execute(
            select(
                *_aggregates(),
                func.count(
                    func.distinct(case((ProdLog.hours_spent.is_not(None), ProdLog.user_id)))
                ),
            ).where(_period(team_id, start, end))
        )
    ).one()
    actual, planned, unplanned, rows, deviations, members = row
    return TeamSummaryStats(
        actual_hours=actual,
        planned_hours=planned,
        unplanned_hours=unplanned,
        log_rows=rows,
        members_with_hours=members,
        deviation_rows=deviations,
    )


def _hours(value: Decimal) -> float:
    return float(value)


async def _member_numbers(
    db: AsyncSession, team_id: int, start: date, end: date
) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(ProdLog.user_id, *_aggregates())
        .where(_period(team_id, start, end))
        .group_by(ProdLog.user_id)
    )
    by_user = {user_id: values for user_id, *values in rows.all()}
    out = []
    for member in await dashboard.team_members(db, team_id, by_user):
        actual, planned, unplanned, count, deviations = by_user.get(
            member.id, (ZERO, ZERO, ZERO, 0, 0)
        )
        out.append(
            {
                "username": member.username,
                "current_member": member.is_current_member,
                "actual_hours": _hours(actual),
                "planned_hours": _hours(planned),
                "unplanned_hours": _hours(unplanned),
                "log_rows": count,
                "rows_with_deviation_reason": deviations,
            }
        )
    return out


async def _deviation_numbers(
    db: AsyncSession, team_id: int, start: date, end: date
) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(DeviationReason.label, func.count(ProdLog.id))
        .join(DeviationReason, DeviationReason.id == ProdLog.deviation_reason_id)
        .where(_period(team_id, start, end))
        .group_by(DeviationReason.id, DeviationReason.label)
        .order_by(func.count(ProdLog.id).desc(), DeviationReason.label)
    )
    return [{"reason": label, "rows": count} for label, count in rows.all()]


async def _numbers(
    db: AsyncSession, team_id: int, start: date, end: date, stats: TeamSummaryStats
) -> dict[str, Any]:
    rng = DateRangeQuery(date_from=start, date_to=end)
    scope = dashboard.team_logs(team_id)
    projects = await dashboard.hours_by_project(db, scope, rng)
    categories = await dashboard.hours_by_category(db, scope, rng)
    activities = await dashboard.hours_by_activity(db, scope, rng)
    return {
        "hours_note": "Hours by member, project, category and activity are actual hours.",
        "team": {
            "actual_hours": _hours(stats.actual_hours),
            "planned_hours": _hours(stats.planned_hours),
            "unplanned_hours": _hours(stats.unplanned_hours),
            "log_rows": stats.log_rows,
            "members_with_actual_hours": stats.members_with_hours,
            "rows_with_deviation_reason": stats.deviation_rows,
        },
        "members": await _member_numbers(db, team_id, start, end),
        "top_projects": [
            {"project": p.project.name if p.project else "(no project)", "hours": _hours(p.hours)}
            for p in projects.items[:TOP_ITEMS]
        ],
        "categories": [
            {"category": c.category.label, "hours": _hours(c.hours)}
            for c in categories.items[:TOP_ITEMS]
        ],
        "top_activities": [
            {"activity": a.activity.label, "hours": _hours(a.hours)}
            for a in activities.items[:TOP_ITEMS]
        ],
        "deviation_reasons": await _deviation_numbers(db, team_id, start, end),
    }


# ---------------------------------------------------------------- log remarks


async def remark_lines(
    db: AsyncSession, team_id: int, start: date, end: date, budget: int
) -> tuple[list[str], int]:
    """Rows with remarks or a reason for deviation as JSON lines, most recent first,
    until the next line would take the text over `budget` characters (counting one
    newline per line). Returns (lines, rows left out)."""
    rows = (
        await db.execute(
            select(
                ProdLog.log_date,
                User.username,
                Project.name,
                Activity.label,
                DeviationReason.label,
                ProdLog.is_planned,
                ProdLog.description,
            )
            .join(User, User.id == ProdLog.user_id)
            .join(Activity, Activity.id == ProdLog.activity_id)
            .outerjoin(Project, Project.id == ProdLog.project_id)
            .outerjoin(DeviationReason, DeviationReason.id == ProdLog.deviation_reason_id)
            .where(
                _period(team_id, start, end),
                or_(
                    func.length(func.trim(func.coalesce(ProdLog.description, ""))) > 0,
                    ProdLog.deviation_reason_id.is_not(None),
                ),
            )
            .order_by(ProdLog.log_date.desc(), ProdLog.created_at.desc(), ProdLog.id.desc())
        )
    ).all()
    lines: list[str] = []
    used = 0
    for log_date, username, project, activity, reason, is_planned, remarks in rows:
        item: dict[str, Any] = {
            "date": log_date.isoformat(),
            "member": username,
            "project": project,
            "activity": activity,
        }
        if not is_planned:
            item["unplanned"] = True
        if reason:
            item["reason_for_deviation"] = reason
        text = (remarks or "").strip()
        if text:
            item["remarks"] = text[:MAX_REMARK_CHARS]
        line = to_json(item)
        if used + len(line) + 1 > budget:
            break
        lines.append(line)
        used += len(line) + 1
    return lines, len(rows) - len(lines)


# ---------------------------------------------------------------- summaries


def _out_query() -> Any:
    return select(AISummary).options(selectinload(AISummary.requester))


async def _cached(db: AsyncSession, data: TeamSummaryRequest) -> AISummary | None:
    return await db.scalar(
        _out_query()
        .where(
            AISummary.team_id == data.team_id,
            AISummary.period_start == data.period_start,
            AISummary.period_end == data.period_end,
        )
        .order_by(AISummary.created_at.desc(), AISummary.id.desc())
        .limit(1)
    )


def _out(summary: AISummary) -> TeamSummaryOut:
    return TeamSummaryOut(
        id=summary.id,
        team_id=summary.team_id,
        period_start=summary.period_start,
        period_end=summary.period_end,
        summary_text=summary.summary_text,
        provider=summary.provider,
        model=summary.model,
        requested_by=UserRef.model_validate(summary.requester),
        created_at=summary.created_at,
    )


def _result(summary: AISummary, stats: TeamSummaryStats, *, cached: bool) -> TeamSummaryResult:
    return TeamSummaryResult(**dict(_out(summary)), cached=cached, stats=stats)


async def summarize_team(
    db: AsyncSession, ai: AIClient, user: User, data: TeamSummaryRequest, settings: Settings
) -> TeamSummaryResult:
    await check_team_access(db, user, data.team_id)
    start, end = data.period_start, data.period_end
    stats = await team_stats(db, data.team_id, start, end)
    if not data.regenerate:
        cached = await _cached(db, data)
        if cached is not None:
            return _result(cached, stats, cached=True)
    if stats.log_rows == 0:
        raise AppError(
            422,
            "no_team_logs",
            "This team has no log rows in the period",
            {"period_start": "No log rows in this period"},
        )

    team_name = await db.scalar(select(Team.name).where(Team.id == data.team_id)) or ""
    budget = settings.ai_summary_char_budget
    lines, omitted = await remark_lines(db, data.team_id, start, end, budget)
    prompt = build_prompt(
        team_name=team_name,
        period_start=start,
        period_end=end,
        numbers=await _numbers(db, data.team_id, start, end, stats),
        remark_lines=lines,
        omitted_rows=omitted,
    )
    text = await ai.generate_text(user, AIFeature.TEAM_SUMMARY, system=SYSTEM, prompt=prompt)
    text = text.strip()
    if not text:
        raise AIOutputError()

    provider = ai.provider
    summary = AISummary(
        team_id=data.team_id,
        requested_by=user.id,
        period_start=start,
        period_end=end,
        summary_text=text[:MAX_SUMMARY_CHARS],
        provider=provider.name,
        model=provider.model,
    )
    db.add(summary)
    await db.commit()
    await db.refresh(summary, ["created_at", "requester"])
    return _result(summary, stats, cached=False)


async def list_summaries(
    db: AsyncSession, user: User, params: TeamSummaryQuery
) -> Page[TeamSummaryOut]:
    """Saved summaries of one team, newest first."""
    await check_team_access(db, user, params.team_id)
    where = AISummary.team_id == params.team_id
    total = await db.scalar(select(func.count()).select_from(AISummary).where(where)) or 0
    summaries = await db.scalars(
        _out_query()
        .where(where)
        .order_by(AISummary.created_at.desc(), AISummary.id.desc())
        .limit(params.limit)
        .offset(params.offset)
    )
    return Page[TeamSummaryOut].build([_out(s) for s in summaries.all()], total, params)
