# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Fabricated-citation metrics for ``lint`` and ``gate``.

This is the headline "we catch the LLM hallucinating" evidence. The model
is asked to cite ``file:line`` evidence for every REAL / GHOST / NEW
finding. A fabricated citation is one that does not resolve to a real
line range on disk, OR whose ``evidence_hash`` no longer matches the
cited text (the file changed since the artifact was written). This module
counts those categories per artifact and renders a stable JSON summary
CI can key off.

Every finding falls into exactly one bucket:

  - ``verified``    — citation parses, resolves to a real line range, and
                      supplied hashes/snippets match the current cited text
                      and bound ranges meet the existing evidence limit.
  - ``fabricated``  — citation is present but does NOT resolve on disk
                      (bad path, out-of-range line, malformed format) OR
                      its evidence binding mismatches the current text, is
                      too broad, cannot be read, or changes during checking.
  - ``unresolved``  — UNRESOLVED classifications carry no citation by
                      contract; counted separately so the verified rate
                      isn't penalized for honest "no evidence" answers.

The fabricated count is the number the discipline exists to drive to
zero. ``fabrication_rate`` is ``fabricated / cited`` where ``cited`` is
``verified + fabricated`` (UNRESOLVED excluded — there's nothing to
fabricate when no claim was made).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from antemortem.citations import (
    CitationVerifier,
    evidence_binding_issues,
    verify_citation,
)
from antemortem.schema import AntemortemOutput


@dataclass(frozen=True)
class CitationFinding:
    """One finding's citation-verification verdict."""

    kind: str  # "classification" | "new_trap"
    id: str
    label: str
    citation: str | None
    status: str  # "verified" | "fabricated" | "unresolved"
    reason: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CitationMetrics:
    """Machine-readable verified/fabricated/unresolved citation summary.

    ``schema`` is a stable identifier so a CI consumer can assert the
    contract it parses against; additions stay backward compatible.
    """

    verified: int
    fabricated: int
    unresolved: int
    cited: int  # verified + fabricated (denominator for fabrication_rate)
    total: int  # all findings including UNRESOLVED
    fabrication_rate: float
    verified_rate: float
    findings: list[CitationFinding] = field(default_factory=list)
    schema: str = "antemortem-citation-metrics-v1"

    @property
    def ok(self) -> bool:
        """True iff no fabricated citations were found."""
        return self.fabricated == 0

    def to_json(self, *, include_findings: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "verified": self.verified,
            "fabricated": self.fabricated,
            "unresolved": self.unresolved,
            "cited": self.cited,
            "total": self.total,
            "fabrication_rate": round(self.fabrication_rate, 6),
            "verified_rate": round(self.verified_rate, 6),
            "ok": self.ok,
        }
        if include_findings:
            payload["findings"] = [f.to_json() for f in self.findings]
        return payload

    def to_json_str(self, *, include_findings: bool = True) -> str:
        return json.dumps(
            self.to_json(include_findings=include_findings),
            indent=2,
            sort_keys=True,
        )


def _classify_citation(
    citation: str | None,
    repo_root: Path,
    *,
    evidence_hash: str | None,
    legacy_sha256: str | None = None,
    evidence_snippet: str | None = None,
    verifier: CitationVerifier | None = None,
) -> tuple[str, str]:
    """Return ``(status, reason)`` for one citation.

    ``status`` is ``"verified"`` or ``"fabricated"``. A present
    evidence_hash that no longer matches the cited text is a fabrication
    (stale/altered evidence) even when the line range still resolves.
    """
    verifier = verifier or CitationVerifier(repo_root)
    result = verify_citation(citation or "", repo_root, verifier=verifier)
    if not result.ok or result.parsed is None:
        return "fabricated", result.reason or "citation does not resolve on disk"

    issues = evidence_binding_issues(
        result.parsed, repo_root, evidence_hash=evidence_hash,
        legacy_sha256=legacy_sha256, evidence_snippet=evidence_snippet,
        verifier=verifier,
    )
    return ("fabricated", "; ".join(issues)) if issues else ("verified", "")


def compute_citation_metrics(
    output: AntemortemOutput,
    repo_root: Path,
    *,
    verifier: CitationVerifier | None = None,
) -> CitationMetrics:
    """Compute fabricated-vs-verified citation metrics for one output."""
    verifier = verifier or CitationVerifier(repo_root)
    findings: list[CitationFinding] = []
    verified = fabricated = unresolved = 0

    for c in output.classifications:
        if c.label == "UNRESOLVED":
            unresolved += 1
            findings.append(
                CitationFinding(
                    kind="classification",
                    id=c.id,
                    label=c.label,
                    citation=None,
                    status="unresolved",
                )
            )
            continue
        status, reason = _classify_citation(
            c.citation, repo_root, evidence_hash=c.evidence_hash,
            legacy_sha256=c.evidence_sha256, evidence_snippet=c.evidence_snippet,
            verifier=verifier,
        )
        if status == "verified":
            verified += 1
        else:
            fabricated += 1
        findings.append(
            CitationFinding(
                kind="classification",
                id=c.id,
                label=c.label,
                citation=c.citation,
                status=status,
                reason=reason,
            )
        )

    for nt in output.new_traps:
        status, reason = _classify_citation(
            nt.citation, repo_root, evidence_hash=nt.evidence_hash,
            legacy_sha256=nt.evidence_sha256, evidence_snippet=nt.evidence_snippet,
            verifier=verifier,
        )
        if status == "verified":
            verified += 1
        else:
            fabricated += 1
        findings.append(
            CitationFinding(
                kind="new_trap",
                id=nt.id,
                label=nt.label,
                citation=nt.citation,
                status=status,
                reason=reason,
            )
        )

    cited = verified + fabricated
    total = cited + unresolved
    fabrication_rate = (fabricated / cited) if cited else 0.0
    verified_rate = (verified / cited) if cited else 0.0
    return CitationMetrics(
        verified=verified,
        fabricated=fabricated,
        unresolved=unresolved,
        cited=cited,
        total=total,
        fabrication_rate=fabrication_rate,
        verified_rate=verified_rate,
        findings=findings,
    )


def metrics_from_artifact(artifact_path: Path, repo_root: Path) -> CitationMetrics:
    """Load an artifact JSON and compute its citation metrics.

    Raises ``ValueError`` when the artifact is missing, malformed, or
    fails schema validation — the same failure contract ``evidence`` uses.
    """
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"artifact not found: {artifact_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"artifact is invalid JSON: {exc.msg} at line {exc.lineno}"
        ) from exc
    try:
        output = AntemortemOutput.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(
            f"artifact schema validation failed: {exc.error_count()} issues"
        ) from exc
    return compute_citation_metrics(output, repo_root)
