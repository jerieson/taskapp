"""AI-assisted features. Results are drafts: nothing is saved until the user confirms
through the normal endpoints. Each call counts toward the daily AI limit (429)."""

from fastapi import APIRouter

from app.ai.client import AIClientDep
from app.ai.features import nl_log_entry
from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser
from app.db.session import SessionDep
from app.schemas.ai import LogDraftOut, LogDraftRequest

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
