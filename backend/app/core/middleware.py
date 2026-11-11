import json
import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_payload
from app.core.logging import request_id_var

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "x-request-id"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9\-]{1,64}$")


class RequestContextMiddleware:
    """Assigns a request ID, logs one line per request, and turns unhandled
    exceptions into the standard 500 error response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.encode(), b"").decode("latin-1")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("unhandled_exception")
            if response_started:
                raise
            await _send_internal_error(send_wrapper)
        finally:
            logger.info(
                "request",
                extra={
                    "fields": {
                        "method": scope["method"],
                        "path": _loggable_path(scope),
                        "status": status_code,
                        "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    }
                },
            )
            request_id_var.reset(token)


def _loggable_path(scope: Scope) -> str:
    """Request path with path-parameter values replaced by `{name}`, e.g.
    /api/invites/{token}, so tokens in URLs never reach the logs."""
    params: dict[str, object] = scope.get("path_params") or {}
    if not params:
        return scope["path"]
    by_value = {str(v): k for k, v in params.items()}
    segments = scope["path"].split("/")
    return "/".join(f"{{{by_value[s]}}}" if s in by_value else s for s in segments)


async def _send_internal_error(send: Send) -> None:
    body = json.dumps(error_payload("internal_error", "Internal server error")).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
