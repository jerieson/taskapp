from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.ai.providers.factory import build_provider
from app.api.routers import (
    admin_import,
    admin_invites,
    admin_overview,
    admin_teams,
    admin_users,
    ai,
    auth,
    dashboard,
    health,
    invites,
    log_options,
    lookups,
    password_resets,
    planning,
    process_runs,
    processes,
    prod_logs,
    projects,
    tasks,
    team_dashboard,
    teams,
)
from app.core.config import get_settings
from app.core.csrf import csrf_protect
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import LoginRateLimiter
from app.schemas.errors import ErrorResponse


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    if app.state.llm_provider is not None:
        await app.state.llm_provider.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

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
        lifespan=_lifespan,
    )
    app.state.login_limiter = LoginRateLimiter()
    # None when LLM_PROVIDER is empty; raises AIConfigError on a broken AI config.
    app.state.llm_provider = build_provider(settings)

    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    # Public: health, auth (login/csrf/google; me/logout/change-password need a
    # session), invites, password-resets. Everything else requires get_current_user.
    for module in (
        health,
        auth,
        invites,
        password_resets,
        admin_teams,
        admin_users,
        admin_invites,
        admin_overview,
        admin_import,
        projects,
        log_options,
        tasks,
        prod_logs,
        planning,
        processes,
        process_runs,
        teams,
        team_dashboard,
        dashboard,
        ai,
    ):
        app.include_router(module.router, prefix="/api")
    for router in (
        lookups.categories,
        lookups.statuses,
        lookups.priorities,
        lookups.work_setups,
        lookups.activities,
        lookups.activity_groups,
        lookups.om_projects,
        lookups.deviation_reasons,
    ):
        app.include_router(router, prefix="/api")

    return app


app = create_app()
