from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser, require_role
from app.core.pagination import Page
from app.db.session import SessionDep
from app.models import Role
from app.schemas.password_resets import PasswordResetCreated
from app.schemas.users import AdminUserOut, AdminUserQuery, AdminUserUpdate
from app.services import admin_users as user_service
from app.services import password_resets as reset_service

router = APIRouter(
    prefix="/admin/users", tags=["admin"], dependencies=[Depends(require_role(Role.ADMIN))]
)


@router.get("", response_model=Page[AdminUserOut])
async def list_users(
    params: Annotated[AdminUserQuery, Query()], db: SessionDep
) -> Page[AdminUserOut]:
    return await user_service.list_users(db, params)


@router.patch("/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: int, data: AdminUserUpdate, admin: CurrentUser, db: SessionDep
) -> AdminUserOut:
    """Change role and/or team. Admins have no team; you cannot change your own role."""
    return await user_service.update_user(db, admin, user_id, data)


@router.post("/{user_id}/deactivate", response_model=AdminUserOut)
async def deactivate_user(user_id: int, admin: CurrentUser, db: SessionDep) -> AdminUserOut:
    """Deactivate and revoke all sessions immediately. You cannot deactivate yourself."""
    return await user_service.set_active(db, admin, user_id, active=False)


@router.post("/{user_id}/activate", response_model=AdminUserOut)
async def activate_user(user_id: int, admin: CurrentUser, db: SessionDep) -> AdminUserOut:
    return await user_service.set_active(db, admin, user_id, active=True)


@router.post("/{user_id}/password-reset", response_model=PasswordResetCreated, status_code=201)
async def create_password_reset(
    user_id: int, admin: CurrentUser, db: SessionDep, settings: SettingsDep
) -> PasswordResetCreated:
    """Generate a single-use reset link for the admin to send manually."""
    return await reset_service.create_reset(db, admin, user_id, settings)
