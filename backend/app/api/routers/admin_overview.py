from fastapi import APIRouter, Depends

from app.core.dependencies import require_role
from app.core.pagination import Page, Pagination
from app.db.session import SessionDep
from app.models import Role
from app.schemas.admin_overview import AdminOverview, AIUsageRow
from app.services import admin_overview as service

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(Role.ADMIN))]
)


@router.get("/overview", response_model=AdminOverview)
async def get_overview(db: SessionDep) -> AdminOverview:
    """Counts of users, teams and pending invites."""
    return await service.overview(db)


@router.get("/ai-usage", response_model=Page[AIUsageRow])
async def list_ai_usage(params: Pagination, db: SessionDep) -> Page[AIUsageRow]:
    """AI requests per user over the last 30 days (users without requests are omitted)."""
    return await service.ai_usage(db, params)
