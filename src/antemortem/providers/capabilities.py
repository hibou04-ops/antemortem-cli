# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Provider capability registry.

This module is the source of truth for public provider support claims. README
tables and compatibility docs must match this registry; adapter tests verify
the behavior offline with injected clients.
"""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-opus-4-7",
    "openai": "gpt-4o",
    "gemini": "gemini-2.5-flash",
}


@dataclass(frozen=True)
class ProviderCapability:
    key: str
    display_name: str
    cli: str
    default_model: str
    api_key_env: tuple[str, ...]
    structured_output_path: str
    local_schema_validation: str
    retry_error_handling: str
    known_caveats: str

    @property
    def api_key_display(self) -> str:
        return " / ".join(self.api_key_env)


PROVIDER_CAPABILITIES: tuple[ProviderCapability, ...] = (
    ProviderCapability(
        key="anthropic",
        display_name="Anthropic",
        cli="--provider anthropic",
        default_model=DEFAULT_MODELS["anthropic"],
        api_key_env=("ANTHROPIC_API_KEY",),
        structured_output_path="messages.parse(output_format=...)",
        local_schema_validation="Pydantic validates parsed/dict output before artifact write.",
        retry_error_handling="SDK exceptions and refusals surface as ProviderError.",
        known_caveats="Native Anthropic only; base_url is ignored.",
    ),
    ProviderCapability(
        key="openai",
        display_name="OpenAI",
        cli="--provider openai",
        default_model=DEFAULT_MODELS["openai"],
        api_key_env=("OPENAI_API_KEY",),
        structured_output_path="beta.chat.completions.parse(response_format=...)",
        local_schema_validation="Pydantic validates parsed/dict output before artifact write.",
        retry_error_handling="SDK exceptions, content_filter, missing choices, and missing parsed output surface as ProviderError.",
        known_caveats="Requires models/endpoints that support the SDK structured parse path.",
    ),
    ProviderCapability(
        key="gemini",
        display_name="Gemini",
        cli="--provider gemini",
        default_model=DEFAULT_MODELS["gemini"],
        api_key_env=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        structured_output_path="Google GenAI response_schema with application/json",
        local_schema_validation="Returned JSON is parsed and validated with the same Pydantic artifact schema.",
        retry_error_handling="SDK exceptions, invalid JSON, schema errors, safety blocks, and missing candidates surface as ProviderError.",
        known_caveats="Requires Google GenAI SDK; no OpenAI-compatible base_url path.",
    ),
    ProviderCapability(
        key="openai-compatible",
        display_name="OpenAI-compatible",
        cli="--provider openai --base-url <url>",
        default_model="user-supplied via --model",
        api_key_env=("OPENAI_API_KEY", "or any string for unauthenticated local endpoints"),
        structured_output_path="Same OpenAI parse path via configured base_url",
        local_schema_validation="Pydantic validates parsed/dict output before artifact write.",
        retry_error_handling="Same OpenAI adapter ProviderError handling.",
        known_caveats="Not universal: endpoint must implement the structured parse path; local model fidelity varies and lint remains mandatory.",
    ),
)


def provider_capabilities() -> tuple[ProviderCapability, ...]:
    return PROVIDER_CAPABILITIES


def native_provider_names() -> tuple[str, ...]:
    return tuple(cap.key for cap in PROVIDER_CAPABILITIES if cap.key != "openai-compatible")


def render_provider_matrix(language: str = "en") -> str:
    """Render the public provider matrix from the capability registry."""
    if language == "kr":
        header = (
            "| Provider | CLI | 기본 model | API key env | Structured output path | Contract-tested behavior | Caveats |\n"
            "|---|---|---|---|---|---|---|"
        )
    else:
        header = (
            "| Provider | CLI | Default model | API key env | Structured output path | Contract-tested behavior | Caveats |\n"
            "|---|---|---|---|---|---|---|"
        )
    rows = [
        "| "
        + " | ".join(
            (
                cap.display_name,
                f"`{cap.cli}`",
                f"`{cap.default_model}`",
                " / ".join(f"`{env}`" for env in cap.api_key_env),
                f"`{cap.structured_output_path}`",
                cap.local_schema_validation + " " + cap.retry_error_handling,
                cap.known_caveats,
            )
        )
        + " |"
        for cap in PROVIDER_CAPABILITIES
    ]
    return "\n".join((header, *rows))
