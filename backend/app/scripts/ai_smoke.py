"""Manual check of the configured LLM provider: one real structured call and one real
text call, printing the validated result and token usage. Not part of the test suite.

    make ai-smoke

Talks to the provider directly (no database, no ai_requests row, no daily limit).
"""

import asyncio
import sys
from datetime import date

from pydantic import BaseModel, Field

from app.ai.providers.base import ProviderError
from app.ai.providers.factory import AIConfigError, build_provider
from app.core.config import get_settings


class SmokeLogDraft(BaseModel):
    title: str = Field(description="Short title of the work done")
    hours_spent: float | None = Field(description="Hours spent, null if not stated")
    log_date: date | None = Field(description="Date of the work (YYYY-MM-DD), null if unknown")
    missing_fields: list[str] = Field(description="Fields the text did not mention")


SYSTEM = (
    "You turn a developer's note into a structured work log entry. "
    f"Today's date is {date.today().isoformat()}."
)
PROMPT = "Spent about 2.5 hours yesterday fixing the login redirect bug."


async def main() -> int:
    settings = get_settings()
    try:
        provider = build_provider(settings)
    except AIConfigError as exc:
        print(f"Config error: {exc}")
        return 1
    if provider is None:
        print("LLM_PROVIDER is empty: AI is disabled. Set LLM_* in .env first.")
        return 1

    endpoint = settings.llm_base_url or "(vendor default)"
    print(f"Provider: {provider.name}  model: {provider.model}  endpoint: {endpoint}\n")
    try:
        draft, usage = await provider.generate_structured(SYSTEM, PROMPT, SmokeLogDraft)
        print("Structured call OK:")
        print(draft.model_dump_json(indent=2))
        print(f"Usage: input={usage.input_tokens} output={usage.output_tokens}\n")

        text, usage = await provider.generate_text(
            "Reply in one short sentence.", "Say hello to the team."
        )
        print(f"Text call OK: {text}")
        print(f"Usage: input={usage.input_tokens} output={usage.output_tokens}")
    except ProviderError as exc:
        # Printed locally only; the app's own logs never include the vendor message.
        print(f"FAILED: {type(exc).__name__}: {exc}")
        if exc.__cause__ is not None:
            print(f"  cause: {exc.__cause__!r}")
        return 1
    finally:
        await provider.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
