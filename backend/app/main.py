from fastapi import Depends, FastAPI

from app.api.routers import admin_invites, admin_users, auth, health, invites, password_resets
from app.core.config import get_settings
from app.core.csrf import csrf_protect
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import LoginRateLimiter
from app.schemas.errors import ErrorResponse


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)

    app = FastAPI(
        title="Taskapp API",
        version="0.1.0",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
        # Documents the standard error format for every route (replaces
        # FastAPI's default HTTPValidationError schema in the OpenAPI output).
        responses={
            "4XX": {"model": ErrorResponse, "description": "Client error"},
            "5XX": {"model": ErrorResponse, "description": "Server error"},
        },
        # Every non-GET request must carry the double-submit CSRF token.
        dependencies=[Depends(csrf_protect)],
    )
    app.state.login_limiter = LoginRateLimiter()

    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    # Public: health, auth (login/csrf/google; me/logout/change-password need a
    # session), invites, password-resets. Everything else requires get_current_user.
    for module in (health, auth, invites, password_resets, admin_invites, admin_users):
        app.include_router(module.router, prefix="/api")

    return app


app = create_app()
