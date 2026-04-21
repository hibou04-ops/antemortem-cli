"""OpenAI adapter (also covers OpenAI-compatible endpoints via ``base_url``).

Uses ``beta.chat.completions.parse(response_format=T)`` for schema-enforced
structured output where the Pydantic model is converted to JSON Schema by
the SDK. Compatible with:

- **OpenAI** — default endpoint.
- **Azure OpenAI** — pass ``base_url`` pointing at the Azure resource.
- **Groq / Together.ai / OpenRouter** — same pattern; any endpoint that
  implements the OpenAI chat-completions protocol with structured output.
- **Local models via Ollama** — Ollama's OpenAI-compatible API at
  ``http://localhost:11434/v1`` works as a drop-in.

Prompt caching is automatic on OpenAI (system prompts over ~1024 tokens
cache server-side without explicit markers). Reasoning models (``o1``,
``o3``) have different API shapes and are out of scope for v0.3; use
``gpt-4o``, ``gpt-4.1`` or equivalent for structured output.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from antemortem.providers.base import (
    LLMProvider,
    ProviderError,
    empty_usage,
    normalize_usage,
)

T = TypeVar("T", bound=BaseModel)


class OpenAIProvider:
    """``LLMProvider`` implementation for the OpenAI SDK and compatible endpoints."""

    name = "openai"

    def __init__(
        self,
        *,
        model: str,
        client: Any = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url

        if client is not None:
            self._client = client
            return

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                "The 'openai' package is required for provider='openai'. "
                "Install with `pip install antemortem[openai]` or "
                "`pip install openai`."
            ) from exc

        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs) if kwargs else OpenAI()

    def structured_complete(
        self,
        *,
        system_prompt: str,
        user_content: str,
        output_schema: type[T],
        max_tokens: int = 16000,
    ) -> tuple[T, dict[str, int]]:
        try:
            response = self._client.beta.chat.completions.parse(
                model=self.model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format=output_schema,
            )
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"OpenAI API call failed: {exc}") from exc

        if not getattr(response, "choices", None):
            raise ProviderError("OpenAI SDK returned no choices.")
        choice = response.choices[0]
        message = getattr(choice, "message", None)
        if message is None:
            raise ProviderError("OpenAI SDK returned no message on first choice.")

        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason == "content_filter":
            raise ProviderError(
                "OpenAI refused the classification request (finish_reason=content_filter). "
                "This usually means the spec or traps contain content flagged by the "
                "moderation layer."
            )

        parsed = getattr(message, "parsed", None)
        if parsed is None:
            # In rare cases the SDK returns the content but no parsed object
            # (e.g. if the model's JSON was unparseable). Surface loudly.
            raise ProviderError(
                f"OpenAI returned no parsed object. finish_reason={finish_reason!r}. "
                "This indicates the response did not conform to the response_format schema."
            )
        if not isinstance(parsed, output_schema):
            parsed = output_schema.model_validate(parsed)

        usage = normalize_usage(getattr(response, "usage", None)) or empty_usage()
        return parsed, usage
