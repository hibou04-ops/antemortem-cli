# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Citation parsing and on-disk verification.

The discipline requires every classification to carry a ``path:line`` or
``path:line-line`` citation. This module parses those strings, resolves them
against a repository root, and verifies the cited line range lies within the
file's actual bounds. It does not execute any cited code ??read-only checks.
"""

from __future__ import annotations

import hashlib
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


def read_citation_text(parsed: ParsedCitation, repo_root: Path) -> str | None:
    """Return the text of the cited line range, or None if unreadable.

    Lines are joined with '\\n' and end with a single '\\n'. Used by `run`
    to compute evidence_sha256 at artifact-write time and by `lint` to
    recompute it later for stale-evidence detection.
    """
    file_path = (repo_root / parsed.path).resolve()
    if not file_path.is_file():
        return None
    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if parsed.start < 1 or parsed.end > len(lines):
        return None
    return "\n".join(lines[parsed.start - 1 : parsed.end]) + "\n"


def compute_evidence_sha256(text: str) -> str:
    """SHA-256 hex digest of cited text. UTF-8 encoding."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evidence_sha256_for_citation(
    citation: str, repo_root: Path
) -> str | None:
    """Convenience: parse + read + hash. Returns None if any step fails.

    Used by `run` to populate Classification.evidence_sha256 after the
    LLM call. Failure (unparseable citation, file missing, line out of
    range) returns None — the caller can decide whether to leave the
    field unset or treat that as a coverage problem (it's already caught
    by the lint citation verifier).
    """
    parsed = parse_citation(citation)
    if parsed is None:
        return None
    text = read_citation_text(parsed, repo_root)
    if text is None:
        return None
    return compute_evidence_sha256(text)


@dataclass(frozen=True)
class CitationAudit:
    """Structured outcome of auditing all citations in an output.

    ``ok`` is True iff every non-UNRESOLVED finding cites a path that
    exists, is inside the repo root, and points at a real line range.
    ``violations`` carries the same one-line reasons that lint would
    print, prefixed by the finding id so the run-time error message is
    actionable.

    Used by ``commands/run.py`` to refuse SAFE_TO_PROCEED before the
    decision gate sees the output. The same helper is used by lint
    (post-run) so both code paths agree on what \"verified\" means.
    """

    ok: bool
    violations: list[str]
    checked: int


def audit_output_citations(output, repo_root: Path) -> CitationAudit:
    """Audit every Classification + NewTrap citation in an AntemortemOutput.

    UNRESOLVED classifications are not audited (no citation to verify).
    Every other finding's citation must parse and resolve to a real line
    range inside ``repo_root``.
    """
    violations: list[str] = []
    checked = 0
    for c in output.classifications:
        if c.label == "UNRESOLVED":
            # Schema invariant guarantees citation is None here; nothing to audit.
            continue
        checked += 1
        result = verify_citation(c.citation or "", repo_root)
        if not result.ok:
            violations.append(f"classification {c.id}: {result.reason}")
    for nt in output.new_traps:
        checked += 1
        result = verify_citation(nt.citation, repo_root)
        if not result.ok:
            violations.append(f"new_trap {nt.id}: {result.reason}")
    return CitationAudit(
        ok=len(violations) == 0,
        violations=violations,
        checked=checked,
    )
