from fastapi import FastAPI

from app.api.routers import health
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
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
    )

    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router, prefix="/api")

    return app


app = create_app()
