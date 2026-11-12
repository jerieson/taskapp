"""Auth dependencies used by every protected endpoint."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from app.core.cookies import CSRF_HEADER, SESSION_COOKIE
from app.core.csrf import csrf_error, is_unsafe
from app.core.errors import AppError
from app.core.security import tokens_equal
from app.db.session import SessionDep
from app.models import Role, User
from app.services.auth import AuthContext, get_auth_context


async def get_current_auth(request: Request, db: SessionDep) -> AuthContext:
    """The caller's live session and active user, or 401.

    For non-GET requests the CSRF header must also match the token stored on the
    session (the app-wide `csrf_protect` dependency has already compared it with the
    cookie).
    """
    ctx = await get_auth_context(db, request.cookies.get(SESSION_COOKIE))
    if ctx is None:
        raise AppError(401, "not_authenticated", "Not logged in or session expired")
    if is_unsafe(request) and not tokens_equal(
        request.headers.get(CSRF_HEADER), ctx.session.csrf_token
    ):
        raise csrf_error()
    return ctx


async def get_current_user(ctx: Annotated[AuthContext, Depends(get_current_auth)]) -> User:
    return ctx.user


CurrentAuth = Annotated[AuthContext, Depends(get_current_auth)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: Role) -> Callable[[User], Awaitable[User]]:
    """Dependency that allows only the given roles (403 otherwise).

    Usage: `dependencies=[Depends(require_role(Role.ADMIN))]` on a router.
    """
    allowed = frozenset(roles)

    async def _check(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise AppError(403, "forbidden", "You do not have permission to do this")
        return user

    return _check
