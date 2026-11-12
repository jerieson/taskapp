"""In-memory login rate limiting, keyed by client IP.

Counts failed login attempts in a sliding window. State lives in the process (one
uvicorn worker) and is reset on restart, which is acceptable at this scale.
"""

import math
import time
from collections import deque
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.core.errors import AppError

MAX_FAILURES = 10
WINDOW_SECONDS = 15 * 60
# Bound memory: forget idle IPs once this many are tracked.
_MAX_TRACKED_KEYS = 10_000


def client_ip(request: Request, settings: Settings) -> str:
    """Behind cloudflared the real client IP is in CF-Connecting-IP. That header is
    trivially spoofable when the app is reached directly, so it is only trusted
    when TRUST_PROXY_HEADERS=true."""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("cf-connecting-ip", "").strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


class LoginRateLimiter:
    def __init__(
        self,
        max_failures: int = MAX_FAILURES,
        window_seconds: int = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}

    def _recent(self, key: str) -> deque[float]:
        now = self._clock()
        attempts = self._failures.get(key)
        if attempts is None:
            return deque()
        while attempts and attempts[0] <= now - self.window_seconds:
            attempts.popleft()
        if not attempts:
            del self._failures[key]
        return attempts

    def check(self, key: str) -> None:
        """Raise 429 if `key` has used up its failed attempts."""
        attempts = self._recent(key)
        if len(attempts) >= self.max_failures:
            retry_after = math.ceil(attempts[0] + self.window_seconds - self._clock())
            raise AppError(
                429,
                "too_many_login_attempts",
                "Too many failed login attempts. Try again later.",
                headers={"Retry-After": str(max(retry_after, 1))},
            )

    def record_failure(self, key: str) -> None:
        if len(self._failures) >= _MAX_TRACKED_KEYS:
            for tracked in list(self._failures):
                self._recent(tracked)  # drops the key once all its attempts have expired
        self._failures.setdefault(key, deque()).append(self._clock())


def get_login_limiter(request: Request) -> LoginRateLimiter:
    """One limiter per app instance (created in create_app)."""
    return request.app.state.login_limiter


LoginLimiterDep = Annotated[LoginRateLimiter, Depends(get_login_limiter)]
