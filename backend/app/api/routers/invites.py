"""Public invite endpoints (no login required)."""

from typing import Annotated

from fastapi import APIRouter, Path, Response

from app.core.config import SettingsDep
from app.core.cookies import set_session_cookies
from app.db.session import SessionDep
from app.schemas.auth import MeOut
from app.schemas.invites import InviteAcceptIn, InvitePublicOut
from app.services import invites as invite_service
from app.services.users import to_me

router = APIRouter(prefix="/invites", tags=["invites"])

Token = Annotated[str, Path(max_length=128)]


@router.get("/{token}", response_model=InvitePublicOut)
async def get_invite(token: Token, db: SessionDep) -> InvitePublicOut:
    """Details of a pending invite; 404 `invite_invalid` if used, expired or unknown."""
    return await invite_service.get_public_invite(db, token)


@router.post("/{token}/accept", response_model=MeOut, status_code=201)
async def accept_invite(
    token: Token, data: InviteAcceptIn, response: Response, db: SessionDep, settings: SettingsDep
) -> MeOut:
    """Create the account with username + password and log the new user in.
    (To accept with Google instead, use GET /api/auth/google/login?invite={token}.)"""
    new = await invite_service.accept_invite(db, token, data, settings)
    set_session_cookies(response, settings, new.token, new.csrf_token)
    return await to_me(db, new.user)
