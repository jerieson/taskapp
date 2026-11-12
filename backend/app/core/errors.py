"""Global exception handlers producing the standard error format:

    {"error": {"code": "snake_case_code", "message": "...", "fields": {...}}}

`fields` is present only for validation errors.
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "too_many_requests",
    503: "service_unavailable",
}

# Location prefixes FastAPI puts in front of the field name.
_LOC_SOURCES = {"body", "query", "path", "header", "cookie"}


class AppError(Exception):
    """Raise from services/routers to return a standard error response."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields
        self.headers = headers


def error_payload(code: str, message: str, fields: dict[str, str] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if fields is not None:
        error["fields"] = fields
    return {"error": error}


def _field_name(loc: tuple[int | str, ...]) -> str:
    parts = list(loc)
    if len(parts) > 1 and parts[0] in _LOC_SOURCES:
        parts = parts[1:]
    return ".".join(str(p) for p in parts) or "body"


async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc.code, exc.message, exc.fields),
        headers=exc.headers,
    )


async def _http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _STATUS_CODES.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(code, message),
        headers=exc.headers,
    )


async def _validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields: dict[str, str] = {}
    for err in exc.errors():
        name = _field_name(tuple(err.get("loc", ())))
        # Keep the first message per field.
        fields.setdefault(name, str(err.get("msg", "Invalid value")))
    return JSONResponse(
        status_code=422,
        content=error_payload("validation_error", "Request validation failed", fields),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
