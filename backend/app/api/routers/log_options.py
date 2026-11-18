"""Options for the prod log form's linked dropdowns (every role)."""

from fastapi import APIRouter

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser
from app.db.session import SessionDep
from app.schemas.lookups import LogOptionsOut
from app.services import log_options as service

router = APIRouter(prefix="/log-options", tags=["dropdowns"])


@router.get("", response_model=LogOptionsOut)
async def get_log_options(
    _user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> LogOptionsOut:
    """Active categories, projects (with category links and activity group), activity
    groups (with their active activity ids), activities, O&M projects, work set-ups and
    reasons for deviation, plus the daily hours cap."""
    return await service.get_log_options(db, settings.workday_hours)
