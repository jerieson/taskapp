"""Provider-neutral contract every LLM adapter implements.

Adapters translate vendor SDK results and exceptions into these types, so nothing
outside `app/ai/providers/` knows which vendor is in use.
"""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


class ProviderError(Exception):
    """Base for errors raised by adapters. `usage` is what the failed call consumed."""

    def __init__(self, message: str, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.usage = usage or Usage()


class ProviderOutputError(ProviderError):
    """The model answered, but not with output matching the schema (invalid JSON,
    failed validation, refusal, truncated). Worth one retry."""


class ProviderCallError(ProviderError):
    """The call itself failed (auth, rate limit, timeout, network, 5xx). The SDK has
    already retried transient failures, so this is not retried again."""


class LLMProvider(Protocol):
    # Recorded on every ai_requests / ai_summaries row.
    name: str
    model: str

    async def generate_structured[T: BaseModel](
        self, system: str, user: str, schema: type[T]
    ) -> tuple[T, Usage]:
        """Return output validated against `schema`, or raise ProviderOutputError."""
        ...

    async def generate_text(self, system: str, user: str) -> tuple[str, Usage]: ...

    async def aclose(self) -> None:
        """Release network resources (called at app shutdown)."""
        ...
