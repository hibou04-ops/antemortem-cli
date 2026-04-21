"""Provider adapters for the LLM call boundary.

antemortem-cli is model-agnostic by design: the discipline (enumerate traps
before the model sees the code; require file:line citations verified on
disk) is vendor-neutral, and so is every piece of it except the one
function that actually issues the API call. That function lives behind
``LLMProvider`` — a Protocol that each provider adapter implements.

Supported providers:

- ``anthropic`` — native Anthropic SDK. Uses ``messages.parse(output_format=...)``
  for schema enforcement, ``cache_control={"type": "ephemeral"}`` for prompt
  caching, and adaptive thinking when available.
- ``openai`` — native OpenAI SDK, with ``--base-url`` support. Uses
  ``beta.chat.completions.parse(response_format=...)`` for schema enforcement.
  Automatic prompt caching applies when system prompt exceeds ~1024 tokens.
  Compatible endpoints (Azure OpenAI, Groq, Together.ai, OpenRouter, local
  Ollama via its OpenAI-compatible API) work via ``--base-url``.

The factory function ``make_provider()`` picks the right adapter from a
string name and validates the environment (API key present, SDK installed).
Tests mock ``LLMProvider`` directly; no test needs to import the SDKs.
"""

from __future__ import annotations

from antemortem.providers.base import LLMProvider, ProviderError
from antemortem.providers.factory import DEFAULT_MODELS, make_provider, supported_providers

__all__ = [
    "LLMProvider",
    "ProviderError",
    "DEFAULT_MODELS",
    "make_provider",
    "supported_providers",
]
