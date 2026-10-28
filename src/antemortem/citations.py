# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Citation parsing and on-disk verification.

The discipline requires every classification to carry a ``path:line`` or
``path:line-line`` citation. This module parses those strings, resolves them
against a repository root, and verifies the cited line range lies within the
file's actual bounds. It does not execute any cited code -- read-only checks.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import struct
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

EVIDENCE_HASH_PREFIX = "sha256:"
MAX_EVIDENCE_RANGE_LINES = 40

_CITATION_RE = re.compile(
    r"""^\s*
    (?P<path>[^\s:]+(?:[^\s:]+)*)      # non-whitespace, non-colon path
    :
    (?P<start>\d+)                       # start line (required)
    (?:-(?P<end>\d+))?                   # optional end line
    \s*$""",
    re.VERBOSE,
)
_EVIDENCE_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


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


@dataclass(frozen=True)
class _Snapshot:
    line_count: int
    lines: tuple[str, ...] | None
    selected_range: tuple[int, int]
    selected_text: str
    cache_bytes: int


class CitationVerifier:
    """A bounded, single-operation source reader, never a process-wide cache.

    Every access re-resolves the path and checks file identity, size and
    nanosecond modification/change timestamps. A detected change invalidates
    that file for the rest of this operation; create a new verifier to retry.
    Files beyond the text/tuple cache budget are streamed, retaining only
    the requested range. Metadata and returned output are outside that budget. This detects ordinary concurrent edits, not adversarial timestamp
    restoration, and does not claim an atomic repository snapshot.
    """

    def __init__(self, repo_root: Path, *, max_cache_bytes: int = 8 * 1024 * 1024):
        if max_cache_bytes < 0:
            raise ValueError("max_cache_bytes must be non-negative")
        self.repo_root = repo_root
        self.max_cache_bytes = max_cache_bytes
        self._paths: dict[str, Path] = {}
        self._identities: dict[Path, tuple[int, ...]] = {}
        self._invalid: set[Path] = set()
        self._cache: OrderedDict[Path, _Snapshot] = OrderedDict()
        self._cache_bytes = 0

    @staticmethod
    def _identity(info: os.stat_result) -> tuple[int, ...]:
        # Python 3.12 Windows stat and fstat can expose different legacy
        # ctime values (creation vs change time). mtime/size/file id are
        # comparable on both paths; POSIX additionally has real change time.
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        return identity if os.name == "nt" else identity + (info.st_ctime_ns,)

    def _snapshot(self, parsed: ParsedCitation) -> tuple[_Snapshot | None, str]:
        try:
            root = self.repo_root.resolve()
            path = (root / parsed.path).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                return None, f"cited path escapes repo root: {parsed.path!r}"
            previous_path = self._paths.setdefault(parsed.path, path)
            if previous_path != path:
                self._invalid.add(previous_path)
                self._invalid.add(path)
            if path in self._invalid:
                return None, f"cited file changed during verification: {parsed.path}"
            info = path.stat()
            if not stat.S_ISREG(info.st_mode):
                return None, f"cited path is not a regular file: {parsed.path}"
            identity = self._identity(info)
            previous = self._identities.setdefault(path, identity)
            if previous != identity:
                self._invalid.add(path)
                old = self._cache.pop(path, None)
                if old is not None:
                    self._cache_bytes -= old.cache_bytes
                return None, f"cited file changed during verification: {parsed.path}"
            cached = self._cache.get(path)
            selected_range = (parsed.start, parsed.end)
            if cached is not None and (
                cached.lines is not None or cached.selected_range == selected_range
            ):
                self._cache.move_to_end(path)
                return cached, ""

            # TextIO's universal-newline iterator defines line numbers for both
            # bounds and evidence. str.splitlines() also splits Unicode VT/FF,
            # which used to make verification and hashing disagree.
            keep_lines = info.st_size <= self.max_cache_bytes
            lines: list[str] | None = [] if keep_lines else None
            lines_cost = sys.getsizeof(())
            selected: list[str] = []
            line_count = 0
            with path.open("r", encoding="utf-8", errors="replace") as source:
                if self._identity(os.fstat(source.fileno())) != identity:
                    self._invalid.add(path)
                    return None, f"cited file changed during verification: {parsed.path}"
                for line_count, line in enumerate(source, 1):
                    line = line.removesuffix("\n")
                    if lines is not None:
                        lines_cost += sys.getsizeof(line) + struct.calcsize("P")
                        if lines_cost <= self.max_cache_bytes:
                            lines.append(line)
                        else:
                            lines = None
                    if parsed.start <= line_count <= parsed.end:
                        selected.append(line)
                if self._identity(os.fstat(source.fileno())) != identity:
                    self._invalid.add(path)
                    return None, f"cited file changed during verification: {parsed.path}"
            if (
                self._identity(path.stat()) != identity
                or (root / parsed.path).resolve() != path
            ):
                self._invalid.add(path)
                return None, f"cited file changed during verification: {parsed.path}"
            text = normalize_evidence_text("\n".join(selected))
            cost = lines_cost if lines is not None else sys.getsizeof(text)
            snapshot = _Snapshot(
                line_count, tuple(lines) if lines is not None else None,
                selected_range, "" if lines is not None else text, cost,
            )
            old = self._cache.pop(path, None)
            if old is not None:
                self._cache_bytes -= old.cache_bytes
            if cost <= self.max_cache_bytes:
                while self._cache and self._cache_bytes + cost > self.max_cache_bytes:
                    _, evicted = self._cache.popitem(last=False)
                    self._cache_bytes -= evicted.cache_bytes
                self._cache[path] = snapshot
                self._cache_bytes += cost
            return snapshot, ""
        except FileNotFoundError:
            return None, f"cited file does not exist: {parsed.path}"
        except (OSError, RuntimeError, ValueError) as exc:
            return None, f"cited file could not be read: {parsed.path} ({exc})"

    def verify(self, citation: str) -> VerificationResult:
        parsed = parse_citation(citation)
        if parsed is None:
            return VerificationResult(
                ok=False,
                reason=f"invalid format -- expected 'path:line' or 'path:line-line', got {citation!r}",
            )
        snapshot, reason = self._snapshot(parsed)
        if snapshot is None:
            return VerificationResult(ok=False, reason=reason, parsed=parsed)
        if parsed.end > snapshot.line_count:
            return VerificationResult(
                ok=False, parsed=parsed,
                reason=(f"line {parsed.start}-{parsed.end} out of range "
                        f"(file {parsed.path} has {snapshot.line_count} lines)"),
            )
        return VerificationResult(ok=True, parsed=parsed)

    def read(self, parsed: ParsedCitation) -> str | None:
        if parsed.start < 1 or parsed.end < parsed.start:
            return None
        snapshot, _ = self._snapshot(parsed)
        if snapshot is None or parsed.end > snapshot.line_count:
            return None
        if snapshot.lines is not None:
            return normalize_evidence_text("\n".join(snapshot.lines[parsed.start - 1:parsed.end]))
        return snapshot.selected_text


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

    try:
        start = int(match.group("start"))
        end_raw = match.group("end")
        end = int(end_raw) if end_raw is not None else start
    except ValueError:
        return None

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


def verify_citation(
    citation: str, repo_root: Path, *, verifier: CitationVerifier | None = None,
) -> VerificationResult:
    """Verify location; an optional operation-scoped verifier reuses reads."""
    return _verifier_for(repo_root, verifier).verify(citation)


def citation_range_line_count(parsed: ParsedCitation) -> int:
    """Return the inclusive cited range length in lines."""
    return parsed.end - parsed.start + 1


def is_evidence_range_too_large(
    parsed: ParsedCitation,
    *,
    max_lines: int = MAX_EVIDENCE_RANGE_LINES,
) -> bool:
    """Whether the cited range is too broad to serve as bounded evidence."""
    return citation_range_line_count(parsed) > max_lines


def normalize_evidence_text(text: str) -> str:
    """Normalize cited evidence before hashing or snippet comparison.

    Line endings become LF and only trailing whitespace is stripped. Leading
    indentation and internal whitespace remain part of the evidence.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip()


def read_citation_text(
    parsed: ParsedCitation, repo_root: Path, *, verifier: CitationVerifier | None = None,
) -> str | None:
    """Read a cited range using the same line contract as verification."""
    return _verifier_for(repo_root, verifier).read(parsed)


def _verifier_for(repo_root: Path, verifier: CitationVerifier | None) -> CitationVerifier:
    if verifier is None:
        return CitationVerifier(repo_root)
    if verifier.repo_root.resolve() != repo_root.resolve():
        raise ValueError("CitationVerifier belongs to a different repo root")
    return verifier


def compute_evidence_sha256(text: str) -> str:
    """Bare SHA-256 hex digest of normalized cited text. UTF-8 encoding.

    Kept for compatibility with earlier ``evidence_sha256`` artifacts.
    New public artifacts should use ``compute_evidence_hash``.
    """
    normalized = normalize_evidence_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_evidence_hash(text: str) -> str:
    """Evidence hash in the public ``sha256:<hex>`` format."""
    return EVIDENCE_HASH_PREFIX + compute_evidence_sha256(text)


def is_valid_evidence_hash(value: str) -> bool:
    """Return True when ``value`` matches ``sha256:<64 lowercase hex>``."""
    return _EVIDENCE_HASH_RE.match(value) is not None


def evidence_binding_issues(
    parsed: ParsedCitation,
    repo_root: Path,
    *,
    evidence_hash: str | None = None,
    legacy_sha256: str | None = None,
    evidence_snippet: str | None = None,
    strict_evidence: bool = False,
    verifier: CitationVerifier | None = None,
) -> list[str]:
    """Shared lint/metrics contract for content bindings, not claim truth."""
    issues: list[str] = []
    if strict_evidence and not evidence_hash:
        issues.append("missing evidence_hash")
    if strict_evidence or evidence_hash or legacy_sha256 or evidence_snippet:
        if is_evidence_range_too_large(parsed):
            issues.append(
                f"cited range too large ({citation_range_line_count(parsed)} lines; "
                f"max {MAX_EVIDENCE_RANGE_LINES})"
            )
    text = read_citation_text(parsed, repo_root, verifier=verifier)
    if text is None:
        return issues + ["cited text could not be read for evidence check"]
    if evidence_hash:
        if not is_valid_evidence_hash(evidence_hash) or compute_evidence_hash(text) != evidence_hash:
            issues.append("evidence_hash mismatch (cited text changed since artifact write)")
    elif legacy_sha256 and compute_evidence_sha256(text) != legacy_sha256:
        issues.append("legacy evidence_sha256 hash mismatch (cited text changed since artifact write)")
    if evidence_snippet is not None:
        snippet = normalize_evidence_text(evidence_snippet)
        if not snippet or snippet not in text:
            issues.append("snippet not found in cited range")
    return issues


def evidence_hash_for_citation(
    citation: str, repo_root: Path, *, verifier: CitationVerifier | None = None,
) -> str | None:
    """Parse + verify + read + hash. Returns None if any step fails."""
    verifier = verifier or CitationVerifier(repo_root)
    verification = verify_citation(citation, repo_root, verifier=verifier)
    if not verification.ok or verification.parsed is None:
        return None
    text = read_citation_text(verification.parsed, repo_root, verifier=verifier)
    if text is None:
        return None
    return compute_evidence_hash(text)


def evidence_sha256_for_citation(
    citation: str, repo_root: Path
) -> str | None:
    """Compatibility helper returning a bare SHA-256 digest."""
    digest = evidence_hash_for_citation(citation, repo_root)
    if digest is None:
        return None
    return digest.removeprefix(EVIDENCE_HASH_PREFIX)


@dataclass(frozen=True)
class CitationAudit:
    """Structured outcome of auditing all citations in an output.

    ``ok`` is True iff every non-UNRESOLVED finding cites a path that
    exists, is inside the repo root, points at a real line range, and
    satisfies the supplied content bindings and their range limit.
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


def audit_output_citations(
    output, repo_root: Path, *, verifier: CitationVerifier | None = None,
) -> CitationAudit:
    """Audit every Classification + NewTrap citation in an AntemortemOutput.

    UNRESOLVED classifications are not audited (no citation to verify).
    Every other finding's citation must parse and resolve to a real line
    range inside ``repo_root``. Supplied hashes/snippets are also checked.
    """
    verifier = verifier or CitationVerifier(repo_root)
    violations: list[str] = []
    checked = 0
    for c in output.classifications:
        if c.label == "UNRESOLVED":
            # Schema invariant guarantees citation is None here; nothing to audit.
            continue
        checked += 1
        result = verify_citation(c.citation or "", repo_root, verifier=verifier)
        if not result.ok:
            violations.append(f"classification {c.id}: {result.reason}")
        elif result.parsed is not None:
            violations.extend(
                f"classification {c.id}: {issue}" for issue in evidence_binding_issues(
                    result.parsed, repo_root, evidence_hash=c.evidence_hash,
                    legacy_sha256=c.evidence_sha256, evidence_snippet=c.evidence_snippet,
                    verifier=verifier,
                )
            )
    for nt in output.new_traps:
        checked += 1
        result = verify_citation(nt.citation, repo_root, verifier=verifier)
        if not result.ok:
            violations.append(f"new_trap {nt.id}: {result.reason}")
        elif result.parsed is not None:
            violations.extend(
                f"new_trap {nt.id}: {issue}" for issue in evidence_binding_issues(
                    result.parsed, repo_root, evidence_hash=nt.evidence_hash,
                    legacy_sha256=nt.evidence_sha256, evidence_snippet=nt.evidence_snippet,
                    verifier=verifier,
                )
            )
    return CitationAudit(
        ok=len(violations) == 0,
        violations=violations,
        checked=checked,
    )
