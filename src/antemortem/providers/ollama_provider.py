# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Ollama adapter — local models, no API key.

Ollama runs open-weight models on the user's own machine. This adapter
targets Ollama's native ``/api/chat`` endpoint via the ``ollama`` Python
SDK, requesting structured output by passing the Pydantic model's JSON
Schema as the ``format`` argument (Ollama's structured-output mode). The
returned JSON is validated against the same ``AntemortemOutput`` Pydantic
model every other provider uses, so the discipline (schema-enforced
output, disk-verified citations) is identical.

Why a dedicated adapter instead of ``--provider openai --base-url``:

- No API key. Ollama is unauthenticated by default; this adapter never
  requires ``OPENAI_API_KEY`` or any secret.
- Native structured output. The ``ollama`` SDK's ``format=<json schema>``
  path is the documented way to get schema-bound JSON from local models;
  it does not depend on a model implementing OpenAI's ``beta.parse``
  protocol, which most local models do not.
- Local-fidelity caveat surfaced honestly: small local models hallucinate
  citations more often, so ``lint`` is doubly important here.

The ``ollama`` package is imported lazily so the dependency is optional —
installing antemortem does not pull it in. Tests inject a mock client and
never import the SDK.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from antemortem.providers.base import (
    LLMProvider,
    ProviderError,
    empty_usage,
    normalize_usage,
)

T = TypeVar("T", bound=BaseModel)

DEFAULT_OLLAMA_HOST = "http://localhost:11434"


class OllamaProvider:
    """``LLMProvider`` implementation for local models served by Ollama."""

    name = "ollama"

    def __init__(
        self,
        *,
        model: str,
        client: Any = None,
        api_key: str | None = None,  # accepted + ignored; Ollama is keyless.
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url or DEFAULT_OLLAMA_HOST

        if client is not None:
            self._client = client
            return

        try:
            from ollama import Client
        except ImportError as exc:  # pragma: no cover - exercised via message contract
            raise ProviderError(
                "The 'ollama' package is required for provider='ollama'. "
                "Install with `pip install ollama` and start the Ollama daemon "
                "(`ollama serve`), then pull a model (`ollama pull llama3.1`)."
            ) from exc

        self._client = Client(host=self.base_url)

    def structured_complete(
        self,
        *,
        system_prompt: str,
        user_content: str,
        output_schema: type[T],
        max_tokens: int = 16000,
    ) -> tuple[T, dict[str, int]]:
        schema = output_schema.model_json_schema()
        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                format=schema,
                options={"num_predict": max_tokens},
            )
        except Exception as exc:  # pragma: no cover - network/daemon failures
            raise ProviderError(
                f"Ollama call failed: {exc}. Is the Ollama daemon running at "
                f"{self.base_url}? Try `ollama serve` and `ollama pull {self.model}`."
            ) from exc

        content = _extract_content(response)
        if not content:
            raise ProviderError(
                "Ollama returned an empty response. The model may not support "
                "structured output; try a larger instruct model."
            )
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"Ollama returned non-JSON content despite the schema format "
                f"request: {exc}. Local model fidelity varies; lint remains "
                "mandatory."
            ) from exc
        try:
            parsed = output_schema.model_validate(data)
        except ValidationError as exc:
            raise ProviderError(
                f"Ollama output did not conform to the requested schema "
                f"({exc.error_count()} issues). Try a stronger local model."
            ) from exc

        usage = _ollama_usage(response) or empty_usage()
        return parsed, usage


def _extract_content(response: Any) -> str:
    """Pull the assistant message text out of an Ollama chat response.

    Ollama responses are dict-like (``{"message": {"content": ...}}``) but
    newer SDK versions return typed objects with attribute access; handle
    both.
    """
    message = _get(response, "message")
    if message is None:
        return ""
    content = _get(message, "content")
    return content or ""


def _ollama_usage(response: Any) -> dict[str, int]:
    """Map Ollama's eval-count fields onto the canonical usage dict.

    Ollama reports ``prompt_eval_count`` (input) and ``eval_count``
    (output). Ollama has no server-side prompt cache, so cache counters
    stay 0.
    """
    prompt = _get(response, "prompt_eval_count") or 0
    completion = _get(response, "eval_count") or 0
    return normalize_usage(
        {
            "input_tokens": int(prompt),
            "output_tokens": int(completion),
        }
    )


def _get(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
