"""CSRF protection (double-submit token) for every non-GET request.

Two layers:
1. `csrf_protect` (an app-wide dependency): the X-CSRF-Token header must equal the
   csrf_token cookie. This covers public endpoints too (login, invite acceptance,
   password reset), using the pre-session token from GET /api/auth/csrf.
2. `get_current_auth` (app/core/dependencies.py) additionally requires the header to
   equal the csrf_token stored on the session, binding the token to the session.
"""

from fastapi import Request

from app.core.cookies import CSRF_COOKIE, CSRF_HEADER
from app.core.errors import AppError
from app.core.security import tokens_equal

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def csrf_error() -> AppError:
    return AppError(403, "csrf_failed", "Missing or invalid CSRF token")


def is_unsafe(request: Request) -> bool:
    return request.method not in SAFE_METHODS


async def csrf_protect(request: Request) -> None:
    if not is_unsafe(request):
        return
    if not tokens_equal(request.headers.get(CSRF_HEADER), request.cookies.get(CSRF_COOKIE)):
        raise csrf_error()
