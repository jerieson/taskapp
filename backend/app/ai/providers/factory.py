"""Pick the adapter named in LLM_PROVIDER.

To add a provider: implement `LLMProvider` in a new module here and register a
builder in `_BUILDERS` (see README, "Adding an LLM provider").
"""

from collections.abc import Callable

from app.ai.providers.base import LLMProvider
from app.ai.providers.openai_compat import OpenAICompatibleProvider
from app.core.config import Settings


class AIConfigError(RuntimeError):
    """Invalid AI configuration; raised at startup so the app does not boot half-configured."""


def _openai(settings: Settings) -> LLMProvider:
    return OpenAICompatibleProvider(
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        base_url=settings.llm_base_url or None,
        timeout=settings.llm_timeout_seconds,
    )


_BUILDERS: dict[str, Callable[[Settings], LLMProvider]] = {
    "openai": _openai,
}


def build_provider(settings: Settings) -> LLMProvider | None:
    """The configured provider, or None when LLM_PROVIDER is empty (AI disabled)."""
    name = settings.llm_provider
    if not name:
        return None
    builder = _BUILDERS.get(name)
    if builder is None:
        available = ", ".join(sorted(_BUILDERS))
        raise AIConfigError(
            f"LLM_PROVIDER={name!r} has no adapter. Available: {available}. "
            "Leave LLM_PROVIDER empty to disable AI features."
        )
    if not settings.llm_api_key.get_secret_value():
        raise AIConfigError(f"LLM_PROVIDER={name!r} is set but LLM_API_KEY is empty.")
    if not settings.llm_model:
        raise AIConfigError(f"LLM_PROVIDER={name!r} is set but LLM_MODEL is empty.")
    return builder(settings)
