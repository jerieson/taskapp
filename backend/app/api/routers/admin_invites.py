from fastapi import APIRouter, Depends

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser, require_role
from app.core.pagination import Page, Pagination
from app.db.session import SessionDep
from app.models import Role
from app.schemas.invites import InviteCreate, InviteCreated, InviteOut
from app.services import invites as invite_service

router = APIRouter(
    prefix="/admin/invites", tags=["admin"], dependencies=[Depends(require_role(Role.ADMIN))]
)


@router.post("", response_model=InviteCreated, status_code=201)
async def create_invite(
    data: InviteCreate, admin: CurrentUser, db: SessionDep, settings: SettingsDep
) -> InviteCreated:
    """`invite_url` is returned only here; only a hash of the token is stored."""
    return await invite_service.create_invite(db, admin, data, settings)


@router.get("", response_model=Page[InviteOut])
async def list_invites(params: Pagination, db: SessionDep) -> Page[InviteOut]:
    return await invite_service.list_invites(db, params)


@router.delete("/{invite_id}", status_code=204)
async def delete_invite(invite_id: int, db: SessionDep) -> None:
    """Revoke an invite that has not been accepted."""
    await invite_service.delete_invite(db, invite_id)
