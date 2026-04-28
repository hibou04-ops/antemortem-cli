# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Citation parsing and on-disk verification.

The discipline requires every classification to carry a ``path:line`` or
``path:line-line`` citation. This module parses those strings, resolves them
against a repository root, and verifies the cited line range lies within the
file's actual bounds. It does not execute any cited code ??read-only checks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_CITATION_RE = re.compile(
    r"""^\s*
    (?P<path>[^\s:]+(?:[^\s:]+)*)      # non-whitespace, non-colon path
    :
    (?P<start>\d+)                       # start line (required)
    (?:-(?P<end>\d+))?                   # optional end line
    \s*$""",
    re.VERBOSE,
)


@dataclass(frozen=True)
class ParsedCitation:
    """A parsed citation reference."""

    path: str
    start: int
    end: int  # equals start for single-line citations


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying a citation against disk."""

    ok: bool
    reason: str = ""
    parsed: ParsedCitation | None = None


def parse_citation(citation: str) -> ParsedCitation | None:
    """Parse a ``path:line`` or ``path:line-line`` citation string.

    Returns ``None`` when the citation does not match the expected shape.
    """
    if not citation:
        return None
    # Normalize Windows backslashes to forward slashes for uniform handling.
    normalized = citation.replace("\\", "/").strip()
    match = _CITATION_RE.match(normalized)
    if match is None:
        return None

    start = int(match.group("start"))
    end_raw = match.group("end")
    end = int(end_raw) if end_raw is not None else start

    if start < 1 or end < start:
        return None

    return ParsedCitation(path=match.group("path"), start=start, end=end)


def count_lines(path: Path) -> int:
    """Count newline-terminated lines in a file. Tolerates non-UTF-8 encodings."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return sum(1 for _ in fh)
    except UnicodeDecodeError:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)


def verify_citation(citation: str, repo_root: Path) -> VerificationResult:
    """Check that ``citation`` resolves to a real file:line range within ``repo_root``.

    Returns a ``VerificationResult`` whose ``ok`` field signals whether the
    citation is valid. When ``ok`` is false, ``reason`` explains the failure in
    one line suitable for CLI output.
    """
    parsed = parse_citation(citation)
    if parsed is None:
        return VerificationResult(
            ok=False,
            reason=f"invalid format ??expected 'path:line' or 'path:line-line', got {citation!r}",
        )

    file_path = (repo_root / parsed.path).resolve()
    try:
        root_resolved = repo_root.resolve()
    except FileNotFoundError:
        return VerificationResult(
            ok=False,
            reason=f"--repo directory does not exist: {repo_root}",
            parsed=parsed,
        )

    # Refuse paths that escape the repo root via '..' traversal.
    try:
        file_path.relative_to(root_resolved)
    except ValueError:
        return VerificationResult(
            ok=False,
            reason=f"cited path escapes repo root: {parsed.path!r}",
            parsed=parsed,
        )

    if not file_path.exists():
        return VerificationResult(
            ok=False,
            reason=f"cited file does not exist: {parsed.path}",
            parsed=parsed,
        )
    if not file_path.is_file():
        return VerificationResult(
            ok=False,
            reason=f"cited path is not a regular file: {parsed.path}",
            parsed=parsed,
        )

    line_count = count_lines(file_path)
    if parsed.start > line_count or parsed.end > line_count:
        return VerificationResult(
            ok=False,
            reason=(
                f"line {parsed.start}-{parsed.end} out of range "
                f"(file {parsed.path} has {line_count} lines)"
            ),
            parsed=parsed,
        )

    return VerificationResult(ok=True, parsed=parsed)
