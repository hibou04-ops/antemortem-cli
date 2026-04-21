"""Provider factory: one call site to construct the right adapter.

Decouples the CLI from the SDK-specific adapter classes. Add a new provider
by (a) implementing the ``LLMProvider`` Protocol in a new module and
(b) registering it in the ``_REGISTRY`` dict below.
"""

from __future__ import annotations

from typing import Any

from antemortem.providers.base import LLMProvider, ProviderError


# Sensible defaults per provider. Users override via --model at the CLI.
# These strings are the model identifiers passed to each vendor's SDK, so
# they are intentionally specific. They should be bumped when vendors
# release new-generation models.
DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-opus-4-7",
    "openai": "gpt-4o",
}


def supported_providers() -> list[str]:
    """Names of providers this build of antemortem-cli supports."""
    return list(_REGISTRY.keys())


def make_provider(
    name: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    client: Any = None,
    **extra: Any,
) -> LLMProvider:
    """Construct a configured ``LLMProvider`` by name.

    Parameters
    ----------
    name:
        Provider identifier. One of ``supported_providers()``.
    model:
        Optional model string override. If None, uses ``DEFAULT_MODELS[name]``.
    api_key:
        Optional API key override. If None, the adapter falls back to the
        vendor's standard environment variable.
    base_url:
        Optional custom endpoint URL. Only meaningful for providers that
        accept one (currently: openai).
    client:
        Optional preconstructed SDK client (used in tests).
    extra:
        Provider-specific knobs (e.g. ``enable_thinking``, ``effort``).
    """
    key = name.lower().strip()
    if key not in _REGISTRY:
        raise ProviderError(
            f"Unknown provider {name!r}. Supported: {', '.join(supported_providers())}"
        )

    builder = _REGISTRY[key]
    resolved_model = model or DEFAULT_MODELS[key]
    return builder(
        model=resolved_model,
        api_key=api_key,
        base_url=base_url,
        client=client,
        **extra,
    )


def _build_anthropic(**kwargs: Any) -> LLMProvider:
    from antemortem.providers.anthropic_provider import AnthropicProvider

    kwargs.pop("base_url", None)  # not meaningful for native Anthropic
    return AnthropicProvider(**kwargs)


def _build_openai(**kwargs: Any) -> LLMProvider:
    from antemortem.providers.openai_provider import OpenAIProvider

    # OpenAI adapter does not accept enable_thinking / effort; strip them
    # if the caller inherited them from generic CLI plumbing.
    kwargs.pop("enable_thinking", None)
    kwargs.pop("effort", None)
    return OpenAIProvider(**kwargs)


_REGISTRY = {
    "anthropic": _build_anthropic,
    "openai": _build_openai,
}
