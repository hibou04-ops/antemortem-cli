"""Anthropic Claude API wrapper for the classification step.

The ``run_classification`` function is the single boundary between the CLI
and the Anthropic SDK. Everything else in the package is framework-free and
testable without the network. Tests mock the ``client`` argument.

Caching strategy:
- The system prompt is rendered with ``cache_control={"type": "ephemeral"}``
  on a top-level system text block. On Opus 4.7 this requires the prompt to
  exceed the 4096-token cacheable-prefix minimum; we size ``SYSTEM_PROMPT``
  accordingly and verify via ``usage.cache_read_input_tokens`` on each call.
- The user payload carries no caching control — it's volatile (different
  traps each run). A second breakpoint on the files block is a v0.2.1
  optimization when we add iterative-run UX.

Model and sampling:
- ``claude-opus-4-7`` is the only supported model in v0.2 (matches Antemortem
  discipline + enforces a known behavioral contract for the prompt).
- No ``temperature`` / ``top_p`` / ``top_k`` — removed on Opus 4.7.
- ``thinking={"type": "adaptive"}`` — off by default on 4.7; explicitly
  enabled because classification benefits from multi-file chain tracing.
- ``output_config={"effort": "high"}`` — minimum recommended for
  intelligence-sensitive work per Anthropic's migration guide.
"""

from __future__ import annotations

from typing import Any, Protocol

from antemortem.prompts import SYSTEM_PROMPT
from antemortem.schema import AntemortemOutput

MODEL = "claude-opus-4-7"
DEFAULT_MAX_TOKENS = 16000


class _MessagesNamespace(Protocol):
    """Duck-typed interface for the subset of ``anthropic.messages`` we use.

    Accepting a Protocol rather than the concrete class keeps the hot path
    testable without importing ``anthropic`` in unit tests.
    """

    def parse(self, **kwargs: Any) -> Any: ...  # noqa: D401


class _AnthropicLike(Protocol):
    """Minimal interface we need from an Anthropic client instance."""

    messages: _MessagesNamespace


def _build_user_content(
    spec: str,
    traps_table_md: str,
    files: list[tuple[str, str]],
) -> str:
    """Render the user-turn payload as the prompt expects."""
    file_blocks: list[str] = []
    for path, content in sorted(files, key=lambda item: item[0]):
        # Normalize path separators so cache keys don't drift on Windows.
        normalized = path.replace("\\", "/")
        file_blocks.append(f'<file path="{normalized}">\n{content}\n</file>')
    files_section = "\n".join(file_blocks)
    return (
        f"<files>\n{files_section}\n</files>\n\n"
        f"<spec>\n{spec.strip()}\n</spec>\n\n"
        f"<traps>\n{traps_table_md.strip()}\n</traps>"
    )


def _usage_to_dict(usage: Any) -> dict[str, int]:
    """Extract token counts from the SDK's usage object into a plain dict."""
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
    }


def run_classification(
    client: _AnthropicLike,
    spec: str,
    traps_table_md: str,
    files: list[tuple[str, str]],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[AntemortemOutput, dict[str, int]]:
    """Call Claude Opus 4.7 to classify traps against provided files.

    Parameters
    ----------
    client:
        An ``anthropic.Anthropic`` instance (or duck-typed equivalent for
        tests).
    spec:
        Text of the change description from the antemortem document.
    traps_table_md:
        The pre-recon Traps table as a markdown string (raw, including
        header row).
    files:
        List of ``(path, content)`` pairs. Sorted internally so cache
        behavior is deterministic regardless of caller ordering.
    max_tokens:
        Upper bound on output tokens. Defaults to 16000 — the ~8k-output
        typical classification response has ample headroom.

    Returns
    -------
    A tuple ``(output, usage)``:

    - ``output``: a validated ``AntemortemOutput`` instance.
    - ``usage``: ``{"input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"}``.
    """
    user_content = _build_user_content(spec, traps_table_md, files)

    response = client.messages.parse(
        model=MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
        output_format=AntemortemOutput,
    )

    stop_reason = getattr(response, "stop_reason", None)
    if stop_reason == "refusal":
        text = ""
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "")
                break
        raise RuntimeError(
            "Claude refused the classification request. This usually means the "
            "spec or traps contain content flagged by safety filters. "
            f"Response text: {text!r}"
        )

    parsed: AntemortemOutput | None = getattr(response, "parsed_output", None)
    if parsed is None:
        raise RuntimeError(
            "SDK returned no parsed_output. This indicates a schema mismatch or "
            "a malformed response. Raw stop_reason: "
            f"{stop_reason!r}"
        )
    if not isinstance(parsed, AntemortemOutput):
        # Some SDK versions may pass through a dict — coerce defensively.
        parsed = AntemortemOutput.model_validate(parsed)

    usage = _usage_to_dict(getattr(response, "usage", None))
    return parsed, usage
