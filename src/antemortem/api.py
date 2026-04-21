"""Thin wrapper around ``LLMProvider`` for the classification step.

antemortem-cli's discipline is model-agnostic: the guarantees (Pydantic-
enforced output schema, disk-verified citations, stable exit codes) do not
depend on which vendor or model issues the underlying call. This file is
the single seam where the CLI meets the LLM — everything above it treats
the call as an opaque function ``f(system_prompt, user_content) -> AntemortemOutput``.

Tests mock ``LLMProvider`` directly via a ``Protocol`` match; no test needs
to import ``anthropic`` or ``openai``. Runtime constructs the concrete
provider via ``providers.make_provider(name, model=..., ...)``.
"""

from __future__ import annotations

from typing import Any, Protocol

from antemortem.providers.base import LLMProvider
from antemortem.schema import AntemortemOutput

DEFAULT_MAX_TOKENS = 16000


class _AnthropicLike(Protocol):
    """Kept for backward compatibility with older tests.

    New callers should use ``LLMProvider`` directly; this alias is retained
    so existing mocks constructed as ``SimpleNamespace(messages=...)`` still
    resolve during a transition period.
    """

    messages: Any


def _build_user_content(
    spec: str,
    traps_table_md: str,
    files: list[tuple[str, str]],
) -> str:
    """Render the user-turn payload as the frozen system prompt expects."""
    file_blocks: list[str] = []
    for path, content in sorted(files, key=lambda item: item[0]):
        normalized = path.replace("\\", "/")
        file_blocks.append(f'<file path="{normalized}">\n{content}\n</file>')
    files_section = "\n".join(file_blocks)
    return (
        f"<files>\n{files_section}\n</files>\n\n"
        f"<spec>\n{spec.strip()}\n</spec>\n\n"
        f"<traps>\n{traps_table_md.strip()}\n</traps>"
    )


def run_classification(
    provider: LLMProvider,
    spec: str,
    traps_table_md: str,
    files: list[tuple[str, str]],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[AntemortemOutput, dict[str, int]]:
    """Classify traps via the configured ``LLMProvider``.

    Returns ``(output, usage)``. Raises ``ProviderError`` (from the adapter)
    on API failures, refusals, or malformed responses.
    """
    from antemortem.prompts import SYSTEM_PROMPT

    user_content = _build_user_content(spec, traps_table_md, files)
    parsed, usage = provider.structured_complete(
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
        output_schema=AntemortemOutput,
        max_tokens=max_tokens,
    )
    return parsed, usage
