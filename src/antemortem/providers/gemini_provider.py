# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Google Gemini adapter.

Uses the official Google GenAI SDK (`google-genai`) behind the same narrow
``LLMProvider.structured_complete`` contract as the other adapters. Gemini is
asked for JSON using native response schema configuration, then the returned
payload is still validated locally with the requested Pydantic model before it
can reach artifact-writing code.
"""

from __future__ import annotations

import os
from json import JSONDecodeError
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from antemortem.providers.base import (
    LLMProvider,
    ProviderError,
    empty_usage,
    normalize_usage,
)

T = TypeVar("T", bound=BaseModel)


class GeminiProvider:
    """``LLMProvider`` implementation for the Google GenAI SDK."""

    name = "gemini"

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

        resolved_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not resolved_key:
            raise ProviderError(
                "Gemini API key is required for provider='gemini'. Set GEMINI_API_KEY "
                "or GOOGLE_API_KEY, or pass api_key explicitly."
            )

        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - import-time path
            raise ProviderError(
                "The 'google-genai' package is required for provider='gemini'. "
                "Install with `pip install google-genai`."
            ) from exc

        self._client = genai.Client(api_key=resolved_key)

    def structured_complete(
        self,
        *,
        system_prompt: str,
        user_content: str,
        output_schema: type[T],
        max_tokens: int = 16000,
    ) -> tuple[T, dict[str, int]]:
        config: dict[str, Any] = {
            "system_instruction": system_prompt,
            "max_output_tokens": max_tokens,
            "response_mime_type": "application/json",
            "response_schema": output_schema,
        }
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=user_content,
                config=config,
            )
        except Exception as exc:  # pragma: no cover - wrapped for clarity
            raise ProviderError(f"Gemini API call failed: {exc}") from exc

        text = _extract_text(response)
        parsed = _validate_response(response=response, text=text, output_schema=output_schema)
        usage = normalize_usage(getattr(response, "usage_metadata", None)) or empty_usage()
        return parsed, usage


def _validate_response(
    *,
    response: Any,
    text: str,
    output_schema: type[T],
) -> T:
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        try:
            if isinstance(parsed, output_schema):
                return parsed
            return output_schema.model_validate(parsed)
        except ValidationError as exc:
            raise ProviderError(f"Gemini response failed schema validation: {exc}") from exc

    try:
        return output_schema.model_validate_json(text)
    except JSONDecodeError as exc:
        raise ProviderError(f"Gemini returned invalid JSON: {exc}") from exc
    except ValueError as exc:
        message = str(exc)
        if "Invalid JSON" in message or "JSON invalid" in message:
            raise ProviderError(f"Gemini returned invalid JSON: {exc}") from exc
        raise ProviderError(f"Gemini response failed schema validation: {exc}") from exc


def _extract_text(response: Any) -> str:
    safety_reason = _safety_block_reason(response)
    if safety_reason:
        raise ProviderError(f"Gemini refused or safety-blocked the request: {safety_reason}")

    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    candidates = getattr(response, "candidates", None)
    if not candidates:
        raise ProviderError("Gemini SDK returned no candidates and no text.")

    candidate = candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    if str(finish_reason).upper() in {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT"}:
        raise ProviderError(f"Gemini refused or safety-blocked the request: {finish_reason}")

    parts = getattr(getattr(candidate, "content", None), "parts", None) or []
    chunks: list[str] = []
    for part in parts:
        part_text = getattr(part, "text", None)
        if isinstance(part_text, str):
            chunks.append(part_text)
    joined = "".join(chunks).strip()
    if not joined:
        raise ProviderError("Gemini SDK returned no text in the first candidate.")
    return joined


def _safety_block_reason(response: Any) -> str | None:
    prompt_feedback = getattr(response, "prompt_feedback", None)
    if prompt_feedback is None:
        return None
    block_reason = getattr(prompt_feedback, "block_reason", None)
    if block_reason:
        return str(block_reason)
    return None
