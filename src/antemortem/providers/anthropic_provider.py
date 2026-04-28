# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Anthropic adapter.

Uses ``messages.parse(output_format=T)`` for schema-enforced structured
output and ``cache_control={"type": "ephemeral"}`` on the system block for
prompt caching. Adaptive thinking is enabled by default on capable models
(e.g. Opus 4.7 family); the ``effort`` parameter controls reasoning depth.

Model defaults are read from ``providers.factory.DEFAULT_MODELS`` so the
adapter itself is not pinned to a single model string.
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


class AnthropicProvider:
    """``LLMProvider`` implementation for the Anthropic SDK."""

    name = "anthropic"

    def __init__(
        self,
        *,
        model: str,
        client: Any = None,
        api_key: str | None = None,
        enable_thinking: bool = True,
        effort: str = "high",
    ) -> None:
        self.model = model
        self.enable_thinking = enable_thinking
        self.effort = effort

        if client is not None:
            self._client = client
            return

        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - import-time path
            raise ProviderError(
                "The 'anthropic' package is required for provider='anthropic'. "
                "Install with `pip install antemortem[anthropic]` or "
                "`pip install anthropic`."
            ) from exc

        self._client = Anthropic(api_key=api_key) if api_key else Anthropic()

    def structured_complete(
        self,
        *,
        system_prompt: str,
        user_content: str,
        output_schema: type[T],
        max_tokens: int = 16000,
    ) -> tuple[T, dict[str, int]]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": user_content}],
            "output_format": output_schema,
        }
        if self.enable_thinking:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": self.effort}

        try:
            response = self._client.messages.parse(**kwargs)
        except Exception as exc:  # pragma: no cover - wrapped for clarity
            raise ProviderError(f"Anthropic API call failed: {exc}") from exc

        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            text = ""
            for block in getattr(response, "content", []) or []:
                if getattr(block, "type", None) == "text":
                    text = getattr(block, "text", "")
                    break
            raise ProviderError(
                "Anthropic refused the classification request. "
                "This usually means the spec or traps contain content flagged by "
                f"safety filters. Response text: {text!r}"
            )

        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise ProviderError(
                "Anthropic SDK returned no parsed_output. This indicates a schema "
                f"mismatch or malformed response. stop_reason={stop_reason!r}."
            )
        if not isinstance(parsed, output_schema):
            parsed = output_schema.model_validate(parsed)

        usage = normalize_usage(getattr(response, "usage", None)) or empty_usage()
        return parsed, usage
