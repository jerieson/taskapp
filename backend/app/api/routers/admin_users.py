from fastapi import APIRouter, Depends

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser, require_role
from app.db.session import SessionDep
from app.models import Role
from app.schemas.password_resets import PasswordResetCreated
from app.services import password_resets as reset_service

router = APIRouter(
    prefix="/admin/users", tags=["admin"], dependencies=[Depends(require_role(Role.ADMIN))]
)


@router.post("/{user_id}/password-reset", response_model=PasswordResetCreated, status_code=201)
async def create_password_reset(
    user_id: int, admin: CurrentUser, db: SessionDep, settings: SettingsDep
) -> PasswordResetCreated:
    """Generate a single-use reset link for the admin to send manually."""
    return await reset_service.create_reset(db, admin, user_id, settings)
