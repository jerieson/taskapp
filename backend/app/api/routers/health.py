import logging

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import AppError
from app.db.session import SessionDep
from app.schemas.health import HealthOut

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthOut)
async def health(session: SessionDep) -> HealthOut:
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        logger.warning("health_db_unreachable", extra={"fields": {"error": type(exc).__name__}})
        raise AppError(503, "database_unavailable", "Database is not reachable") from exc
    return HealthOut(status="ok", database="ok")
