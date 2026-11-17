"""Typed errors raised by the AI client. They are AppErrors, so routers can let them
propagate and the client gets the standard error response."""

from app.core.errors import AppError


class AIError(AppError):
    pass


class AIDisabledError(AIError):
    def __init__(self) -> None:
        super().__init__(503, "ai_disabled", "AI features are not configured on this server")


class AIDailyLimitError(AIError):
    def __init__(self, limit: int) -> None:
        super().__init__(
            429,
            "ai_daily_limit_exceeded",
            f"Daily AI request limit reached ({limit}). Try again tomorrow.",
        )


class AIOutputError(AIError):
    """The model's output failed validation, including the one retry."""

    def __init__(self) -> None:
        super().__init__(
            502, "ai_invalid_output", "The AI returned an unusable answer. Please try again."
        )


class AIProviderError(AIError):
    """The provider call failed (auth, rate limit, timeout, network, outage)."""

    def __init__(self) -> None:
        super().__init__(
            502, "ai_provider_error", "The AI service is unavailable. Please try again later."
        )
