# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Abstract ``LLMProvider`` Protocol.

The contract every adapter satisfies is a single method: ``structured_complete``.
It takes a system prompt, a user message, and a Pydantic output class; it
returns the parsed object and a usage dict.

The Protocol is intentionally narrow. Nothing provider-specific (thinking
parameters, caching markers, response_format shapes) leaks through. Each
adapter is free to use its vendor's strongest schema-enforcement mechanism
internally ??``messages.parse`` on Anthropic, ``beta.chat.completions.parse``
on OpenAI ??as long as the returned object is a valid instance of
``output_schema``.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ProviderError(RuntimeError):
    """Raised when a provider call fails in a way the caller can surface."""


class LLMProvider(Protocol):
    """Structural interface for LLM adapters.

    A conforming adapter must:

    - Use the vendor's native schema-enforcement path (not client-side parse).
    - Apply the vendor's prompt-caching mechanism where available (explicit
      on Anthropic, automatic on OpenAI).
    - Return usage as a dict with keys: ``input_tokens``, ``output_tokens``,
      ``cache_creation_input_tokens``, ``cache_read_input_tokens``. Missing
      keys are reported as 0.
    - Raise ``ProviderError`` with an actionable message on any failure.

    The Protocol is structural ??implementers do not inherit from it.
    """

    name: str  # short identifier, e.g. "anthropic" / "openai"
    model: str  # resolved model string used on every call

    def structured_complete(
        self,
        *,
        system_prompt: str,
        user_content: str,
        output_schema: type[T],
        max_tokens: int = 16000,
    ) -> tuple[T, dict[str, int]]:
        """Issue one schema-enforced completion.

        Returns ``(parsed, usage)`` where ``parsed`` is an instance of
        ``output_schema`` and ``usage`` is the per-call token breakdown.
        """
        ...


def empty_usage() -> dict[str, int]:
    """Canonical zero-usage dict. Used by mocks and error paths."""
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def normalize_usage(raw: Any) -> dict[str, int]:
    """Coerce a vendor-specific usage object into the canonical dict shape."""
    def _get(name: str) -> int:
        value = getattr(raw, name, 0) if raw is not None else 0
        return int(value or 0)

    # Some SDKs expose usage as a dict-like object instead of attribute-access.
    if isinstance(raw, dict):
        def _get(name: str) -> int:  # noqa: F811
            return int(raw.get(name, 0) or 0)

    # OpenAI reports prompt_tokens / completion_tokens; map them to the
    # canonical anthropic-shaped dict so callers see one schema.
    input_tokens = _get("input_tokens") or _get("prompt_tokens")
    output_tokens = _get("output_tokens") or _get("completion_tokens")
    cache_create = _get("cache_creation_input_tokens")
    cache_read = _get("cache_read_input_tokens")

    # OpenAI nests cache info under prompt_tokens_details.cached_tokens
    if not cache_read and raw is not None:
        details = getattr(raw, "prompt_tokens_details", None)
        if details is None and isinstance(raw, dict):
            details = raw.get("prompt_tokens_details")
        if details is not None:
            if isinstance(details, dict):
                cache_read = int(details.get("cached_tokens", 0) or 0)
            else:
                cache_read = int(getattr(details, "cached_tokens", 0) or 0)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_create,
        "cache_read_input_tokens": cache_read,
    }
