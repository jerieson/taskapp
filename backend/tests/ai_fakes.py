"""FakeProvider: a scripted LLMProvider for tests. No network calls."""

from typing import Any

from pydantic import BaseModel

from app.ai.providers.base import Usage


class FakeProvider:
    """Each call pops the next scripted response: a value to return (BaseModel for
    structured calls, str for text) or an exception to raise."""

    name = "fake"
    model = "fake-model"

    def __init__(self, *responses: Any, usage: Usage | None = None) -> None:
        self.responses: list[Any] = list(responses)
        self.usage = usage or Usage(input_tokens=100, output_tokens=20)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def script(self, *responses: Any) -> None:
        self.responses.extend(responses)

    async def generate_structured[T: BaseModel](
        self, system: str, user: str, schema: type[T]
    ) -> tuple[T, Usage]:
        self.calls.append({"kind": "structured", "system": system, "user": user, "schema": schema})
        return self._next(), self.usage

    async def generate_text(self, system: str, user: str) -> tuple[str, Usage]:
        self.calls.append({"kind": "text", "system": system, "user": user})
        return self._next(), self.usage

    async def aclose(self) -> None:
        self.closed = True

    def _next(self) -> Any:
        if not self.responses:
            raise AssertionError("FakeProvider called more times than scripted")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item
