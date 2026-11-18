"""Prod log export: one person's rows as CSV in the team sheet's column order.

Access (permission matrix in CLAUDE.md): everyone exports their own logs; a manager
exports the rows a member wrote while in the manager's team (the team snapshot); an
admin exports anyone's. Anyone else is reported as 404.

The file opens cleanly in Excel: UTF-8 with a BOM, and cells that a spreadsheet would
read as a formula are prefixed with an apostrophe.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models import (
    Activity,
    Category,
    DeviationReason,
    OmProject,
    ProdLog,
    Project,
    Role,
    User,
    WorkSetup,
)
from app.schemas.prod_logs import LogExportQuery

COLUMNS = (
    "Date",
    "Work Set-Up",
    "Planned Hours",
    "Actual Hours Consumed",
    "Planned",
    "Category",
    "Project",
    "Activity/Task",
    "Project (For O&M)",
    "Reason for Deviation",
    "Remarks",
    "Date Created",
)

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def sheet_date(day: date) -> str:
    """The sheet's date format: 3-Nov-2026."""
    return f"{day.day}-{day.strftime('%b')}-{day.year}"


def _hours(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _cell(value: str | None) -> str:
    """Text as a CSV cell, neutralised if a spreadsheet would treat it as a formula."""
    if not value:
        return ""
    return f"'{value}" if value.startswith(_FORMULA_START) else value


async def _scope(db: AsyncSession, user: User, user_id: int | None) -> tuple[User, int | None]:
    """The person being exported and, for managers, the team snapshot to filter on."""
    if user_id is None or user_id == user.id:
        return user, None
    target = await db.get(User, user_id)
    if target is None or user.role == Role.DEV:
        raise AppError(404, "not_found", "User not found")
    if user.role == Role.ADMIN:
        return target, None
    # Manager: a current member, or a former one with rows under the team.
    team_id = user.team_id
    has_rows = await db.scalar(
        select(ProdLog.id).where(ProdLog.user_id == target.id, ProdLog.team_id == team_id).limit(1)
    )
    if team_id is None or (target.team_id != team_id and has_rows is None):
        raise AppError(404, "not_found", "User not found")
    return target, team_id


async def export_csv(
    db: AsyncSession, user: User, params: LogExportQuery, settings: Settings
) -> tuple[str, bytes]:
    """Return the file name and the CSV bytes, sorted by date then creation."""
    target, team_id = await _scope(db, user, params.user_id)
    stmt = (
        select(
            ProdLog,
            WorkSetup.label,
            Category.label,
            Project.name,
            Activity.label,
            OmProject.label,
            DeviationReason.label,
        )
        .join(WorkSetup, WorkSetup.id == ProdLog.work_setup_id)
        .join(Category, Category.id == ProdLog.category_id)
        .outerjoin(Project, Project.id == ProdLog.project_id)
        .join(Activity, Activity.id == ProdLog.activity_id)
        .outerjoin(OmProject, OmProject.id == ProdLog.om_project_id)
        .outerjoin(DeviationReason, DeviationReason.id == ProdLog.deviation_reason_id)
        .where(
            ProdLog.user_id == target.id,
            ProdLog.log_date >= params.date_from,
            ProdLog.log_date <= params.date_to,
        )
        .order_by(ProdLog.log_date, ProdLog.created_at, ProdLog.id)
    )
    if team_id is not None:
        stmt = stmt.where(ProdLog.team_id == team_id)

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    for log, setup, category, project, activity, om_project, reason in (
        await db.execute(stmt)
    ).all():
        created: datetime = log.created_at
        writer.writerow(
            [
                sheet_date(log.log_date),
                _cell(setup),
                _hours(log.planned_hours),
                _hours(log.hours_spent),
                "Planned" if log.is_planned else "Unplanned",
                _cell(category),
                _cell(project),
                _cell(activity),
                _cell(om_project),
                _cell(reason),
                _cell(log.description),
                sheet_date(created.astimezone(settings.tz).date()),
            ]
        )
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", target.username)
    filename = (
        f"{safe_name}_{params.date_from.isoformat()}_{params.date_to.isoformat()}"
        "_productivity_log.csv"
    )
    return filename, out.getvalue().encode("utf-8-sig")
