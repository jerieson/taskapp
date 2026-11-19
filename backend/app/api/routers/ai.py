"""AI-assisted features. Results are drafts: nothing is saved until the user confirms
through the normal endpoints. Each call counts toward the daily AI limit (429)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.ai.client import AIClientDep
from app.ai.features import nl_log_entry, team_summary
from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser
from app.core.pagination import Page
from app.db.session import SessionDep
from app.schemas.ai import (
    LogDraftOut,
    LogDraftRequest,
    TeamSummaryOut,
    TeamSummaryQuery,
    TeamSummaryRequest,
    TeamSummaryResult,
)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/log-draft", response_model=LogDraftOut)
async def log_draft(
    data: LogDraftRequest,
    user: CurrentUser,
    db: SessionDep,
    ai: AIClientDep,
    settings: SettingsDep,
) -> LogDraftOut:
    """Draft prod log rows (one or many) from free text. The text is sent to the
    configured AI provider. Nothing is saved: confirm with POST /api/logs/bulk.

    Errors: 503 `ai_disabled`, 429 `ai_daily_limit_exceeded`, 502 `ai_invalid_output`
    or `ai_provider_error`."""
    return await nl_log_entry.draft_log(db, ai, user, data.text, settings)


@router.post("/team-summary", response_model=TeamSummaryResult)
async def create_team_summary(
    data: TeamSummaryRequest,
    user: CurrentUser,
    db: SessionDep,
    ai: AIClientDep,
    settings: SettingsDep,
) -> TeamSummaryResult:
    """AI narrative of a team's work over a period (managers: own team, admins: any
    team, devs: 403). Figures are computed from the database; the AI writes prose only.
    Log remarks are sent to the configured AI provider.

    Returns the saved summary for the same team and period (`cached`, no AI call)
    unless `regenerate` is true. `stats` are the database figures, computed now.

    Errors: 403 for devs, 404 `not_found` for a team the caller cannot see, 422
    `no_team_logs`, plus the AI errors of /ai/log-draft."""
    return await team_summary.summarize_team(db, ai, user, data, settings)


@router.get("/team-summaries", response_model=Page[TeamSummaryOut])
async def list_team_summaries(
    params: Annotated[TeamSummaryQuery, Query()], user: CurrentUser, db: SessionDep
) -> Page[TeamSummaryOut]:
    """Saved summaries of one team, newest first."""
    return await team_summary.list_summaries(db, user, params)
