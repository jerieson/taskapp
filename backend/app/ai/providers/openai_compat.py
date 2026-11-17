"""Adapter for OpenAI and any OpenAI-compatible endpoint (gateways, Ollama, vLLM, ...).

Uses Chat Completions rather than the newer Responses API because compatible
endpoints almost always implement Chat Completions, and often nothing else.

Structured output: a strict `json_schema` response_format built from the Pydantic
model. The schema is also written into the system prompt, because some compatible
backends ignore response_format. The reply is then validated here with Pydantic.
"""

import json
import logging
import re
from typing import Any

import httpx2
import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError

from app.ai.providers.base import ProviderCallError, ProviderOutputError, Usage

logger = logging.getLogger("app.ai.openai")

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: float = 120.0,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.model = model
        # The SDK retries connection errors, 408/409/429 and 5xx (2 retries, backoff).
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or None,
            timeout=timeout,
            max_retries=2,
            http_client=http_client,
        )
        # Flipped off if the endpoint rejects json_schema response_format; the schema
        # in the prompt plus Pydantic validation still apply.
        self._json_schema_supported = True

    async def generate_structured[T: BaseModel](
        self, system: str, user: str, schema: type[T]
    ) -> tuple[T, Usage]:
        tool = openai.pydantic_function_tool(schema)["function"]
        json_schema: dict[str, Any] = tool["parameters"]
        messages = _messages(
            f"{system}\n\n"
            "Respond with one JSON object that matches this JSON schema. "
            "Output only the JSON object, with no other text.\n"
            f"{json.dumps(json_schema, separators=(',', ':'))}",
            user,
        )
        response = await self._structured_call(messages, tool["name"], json_schema)
        usage = _usage(response)
        content = _content(response, usage)
        try:
            return schema.model_validate_json(_extract_json(content)), usage
        except ValidationError as exc:
            raise ProviderOutputError(
                f"Output did not match {schema.__name__} ({exc.error_count()} errors)", usage
            ) from exc

    async def generate_text(self, system: str, user: str) -> tuple[str, Usage]:
        response = await self._call(_messages(system, user))
        usage = _usage(response)
        return _content(response, usage).strip(), usage

    async def aclose(self) -> None:
        await self._client.close()

    async def _structured_call(
        self, messages: list[ChatCompletionMessageParam], name: str, json_schema: dict[str, Any]
    ) -> ChatCompletion:
        if self._json_schema_supported:
            response_format: Any = {
                "type": "json_schema",
                "json_schema": {"name": name, "schema": json_schema, "strict": True},
            }
            try:
                return await self._call(messages, response_format=response_format)
            except ProviderCallError as exc:
                cause = exc.__cause__
                if not (isinstance(cause, openai.BadRequestError) and _mentions_json_schema(cause)):
                    raise
                logger.warning(
                    "Endpoint rejected json_schema response_format; using json_object",
                    extra={"fields": {"model": self.model}},
                )
                self._json_schema_supported = False
        return await self._call(messages, response_format={"type": "json_object"})

    async def _call(
        self, messages: list[ChatCompletionMessageParam], **kwargs: Any
    ) -> ChatCompletion:
        try:
            return await self._client.chat.completions.create(
                model=self.model, messages=messages, **kwargs
            )
        except openai.APIError as exc:
            # Class and status only: vendor messages can echo part of the API key.
            raise ProviderCallError(_describe(exc)) from exc


def _messages(system: str, user: str) -> list[ChatCompletionMessageParam]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _usage(response: ChatCompletion) -> Usage:
    if response.usage is None:  # some compatible endpoints omit it
        return Usage()
    return Usage(
        input_tokens=response.usage.prompt_tokens or 0,
        output_tokens=response.usage.completion_tokens or 0,
    )


def _content(response: ChatCompletion, usage: Usage) -> str:
    if not response.choices:
        raise ProviderOutputError("Response had no choices", usage)
    choice = response.choices[0]
    if choice.message.refusal:
        raise ProviderOutputError("Model refused the request", usage)
    if choice.finish_reason == "length":
        raise ProviderOutputError("Output was cut off at the token limit", usage)
    if not choice.message.content:
        raise ProviderOutputError("Response was empty", usage)
    return choice.message.content


def _extract_json(content: str) -> str:
    """Tolerate code fences or stray prose around the object (some models add them)."""
    text = content.strip()
    if fenced := _FENCE.match(text):
        text = fenced.group(1)
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return text


def _mentions_json_schema(exc: openai.BadRequestError) -> bool:
    text = str(exc).lower()
    return "response_format" in text or "json_schema" in text


def _describe(exc: openai.APIError) -> str:
    if isinstance(exc, openai.APIStatusError):
        return f"{type(exc).__name__} (HTTP {exc.status_code})"
    return type(exc).__name__
