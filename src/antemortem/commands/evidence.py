# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Inspect and maintain evidence hashes for existing artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from antemortem.citations import (
    compute_evidence_hash,
    compute_evidence_sha256,
    is_evidence_range_too_large,
    is_valid_evidence_hash,
    normalize_evidence_text,
    read_citation_text,
    verify_citation,
)
from antemortem.schema import AntemortemOutput


@dataclass
class EvidenceItem:
    kind: str
    id: str
    label: str
    citation: str | None
    status: str
    issues: list[str] = field(default_factory=list)
    current_hash: str | None = None
    computed_hash: str | None = None
    evidence_snippet: str | None = None
    cited_text: str | None = None
    written: bool = False

    def as_json(self, *, show_snippets: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "citation": self.citation,
            "computed_hash": self.computed_hash,
            "current_hash": self.current_hash,
            "id": self.id,
            "issues": self.issues,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "written": self.written,
        }
        if self.evidence_snippet is not None:
            payload["evidence_snippet"] = self.evidence_snippet
        if show_snippets and self.cited_text is not None:
            payload["cited_text"] = self.cited_text
        return payload


@dataclass
class EvidenceReport:
    artifact: Path
    repo_root: Path
    items: list[EvidenceItem] = field(default_factory=list)
    changed: bool = False

    def counts(self) -> dict[str, int]:
        counts = {
            "checked": 0,
            "invalid_citations": 0,
            "matching_hashes": 0,
            "mismatched_hashes": 0,
            "missing_hashes": 0,
            "oversized_ranges": 0,
            "snippet_mismatches": 0,
            "unresolved_skipped": 0,
            "written_hashes": 0,
        }
        for item in self.items:
            if item.status == "unresolved_skipped":
                counts["unresolved_skipped"] += 1
                continue
            counts["checked"] += 1
            if "invalid citation" in item.issues:
                counts["invalid_citations"] += 1
            if "hash matches" in item.issues:
                counts["matching_hashes"] += 1
            if "hash mismatch" in item.issues:
                counts["mismatched_hashes"] += 1
            if "missing evidence_hash" in item.issues:
                counts["missing_hashes"] += 1
            if "cited range too large" in item.issues:
                counts["oversized_ranges"] += 1
            if "snippet not found in cited range" in item.issues:
                counts["snippet_mismatches"] += 1
            if item.written:
                counts["written_hashes"] += 1
        return counts

    def ok(self) -> bool:
        counts = self.counts()
        unresolved_missing = counts["missing_hashes"] - counts["written_hashes"]
        return (
            counts["invalid_citations"] == 0
            and counts["mismatched_hashes"] == 0
            and counts["oversized_ranges"] == 0
            and counts["snippet_mismatches"] == 0
            and unresolved_missing == 0
        )

    def as_json(self, *, show_snippets: bool) -> dict[str, Any]:
        return {
            "artifact": str(self.artifact),
            "changed": self.changed,
            "counts": self.counts(),
            "items": [item.as_json(show_snippets=show_snippets) for item in self.items],
            "ok": self.ok(),
            "repo_root": str(self.repo_root),
        }


def inspect_evidence(
    artifact: Path,
    repo_root: Path,
    *,
    write_missing: bool = False,
) -> EvidenceReport:
    """Inspect an artifact and optionally fill missing evidence_hash values."""
    artifact = artifact.resolve()
    repo_resolved = repo_root.resolve()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    try:
        output = AntemortemOutput.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"artifact schema validation failed: {exc.error_count()} issues") from exc

    report = EvidenceReport(artifact=artifact, repo_root=repo_resolved)
    changed = False

    for index, classification in enumerate(output.classifications):
        if classification.label == "UNRESOLVED":
            report.items.append(
                EvidenceItem(
                    kind="classification",
                    id=classification.id,
                    label=classification.label,
                    citation=classification.citation,
                    status="unresolved_skipped",
                )
            )
            continue
        raw = _raw_item(payload, "classifications", index)
        item = _inspect_item(
            kind="classification",
            finding_id=classification.id,
            label=classification.label,
            citation=classification.citation,
            evidence_hash=classification.evidence_hash,
            legacy_sha256=classification.evidence_sha256,
            evidence_snippet=classification.evidence_snippet,
            repo_root=repo_resolved,
        )
        if write_missing and _can_write_missing(item):
            raw["evidence_hash"] = item.computed_hash
            item.status = "written_hash"
            item.written = True
            changed = True
        report.items.append(item)

    for index, new_trap in enumerate(output.new_traps):
        raw = _raw_item(payload, "new_traps", index)
        item = _inspect_item(
            kind="new_trap",
            finding_id=new_trap.id,
            label=new_trap.label,
            citation=new_trap.citation,
            evidence_hash=new_trap.evidence_hash,
            legacy_sha256=new_trap.evidence_sha256,
            evidence_snippet=new_trap.evidence_snippet,
            repo_root=repo_resolved,
        )
        if write_missing and _can_write_missing(item):
            raw["evidence_hash"] = item.computed_hash
            item.status = "written_hash"
            item.written = True
            changed = True
        report.items.append(item)

    if changed:
        artifact.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    report.changed = changed
    return report


def _raw_item(payload: dict[str, Any], key: str, index: int) -> dict[str, Any]:
    items = payload.get(key)
    if not isinstance(items, list) or not isinstance(items[index], dict):
        raise ValueError(f"artifact {key}[{index}] is not an object")
    return items[index]


def _inspect_item(
    *,
    kind: str,
    finding_id: str,
    label: str,
    citation: str | None,
    evidence_hash: str | None,
    legacy_sha256: str | None,
    evidence_snippet: str | None,
    repo_root: Path,
) -> EvidenceItem:
    item = EvidenceItem(
        kind=kind,
        id=finding_id,
        label=label,
        citation=citation,
        status="unchecked",
        current_hash=evidence_hash,
        evidence_snippet=evidence_snippet,
    )
    result = verify_citation(citation or "", repo_root)
    if not result.ok or result.parsed is None:
        item.status = "invalid_citation"
        item.issues.append("invalid citation")
        if result.reason:
            item.issues.append(result.reason)
        return item

    if is_evidence_range_too_large(result.parsed):
        item.issues.append("cited range too large")

    text = read_citation_text(result.parsed, repo_root)
    if text is None:
        item.status = "invalid_citation"
        item.issues.append("invalid citation")
        item.issues.append("cited text could not be read")
        return item

    item.cited_text = text
    item.computed_hash = compute_evidence_hash(text)

    if evidence_hash:
        if is_valid_evidence_hash(evidence_hash) and evidence_hash == item.computed_hash:
            item.issues.append("hash matches")
        else:
            item.issues.append("hash mismatch")
    else:
        item.issues.append("missing evidence_hash")
        if legacy_sha256:
            expected = compute_evidence_sha256(text)
            if legacy_sha256 == expected:
                item.issues.append("legacy evidence_sha256 matches")
            else:
                item.issues.append("legacy evidence_sha256 mismatch")

    if evidence_snippet is not None:
        snippet = normalize_evidence_text(evidence_snippet)
        if not snippet or snippet not in text:
            item.issues.append("snippet not found in cited range")

    item.status = _status_from_issues(item.issues)
    return item


def _status_from_issues(issues: list[str]) -> str:
    if "hash mismatch" in issues:
        return "mismatched_hash"
    if "snippet not found in cited range" in issues:
        return "snippet_mismatch"
    if "cited range too large" in issues:
        return "oversized_range"
    if "missing evidence_hash" in issues:
        return "missing_hash"
    if "hash matches" in issues:
        return "matching_hash"
    return "valid_citation"


def _can_write_missing(item: EvidenceItem) -> bool:
    return (
        item.computed_hash is not None
        and "missing evidence_hash" in item.issues
        and "invalid citation" not in item.issues
        and "cited range too large" not in item.issues
    )


def _render_text(report: EvidenceReport, *, show_snippets: bool) -> str:
    counts = report.counts()
    lines = [
        f"Artifact: {report.artifact}",
        f"Repo: {report.repo_root}",
        (
            "Counts: "
            f"checked={counts['checked']}, "
            f"matching={counts['matching_hashes']}, "
            f"missing={counts['missing_hashes']}, "
            f"mismatched={counts['mismatched_hashes']}, "
            f"snippet_mismatches={counts['snippet_mismatches']}, "
            f"oversized={counts['oversized_ranges']}, "
            f"invalid_citations={counts['invalid_citations']}, "
            f"written={counts['written_hashes']}, "
            f"unresolved_skipped={counts['unresolved_skipped']}"
        ),
    ]
    for item in report.items:
        subject = f"{item.kind} {item.id}"
        if item.status == "unresolved_skipped":
            lines.append(f"- {subject}: UNRESOLVED skipped")
            continue
        detail = "; ".join(item.issues) if item.issues else item.status
        lines.append(f"- {subject}: {detail}")
        if item.computed_hash:
            lines.append(f"  computed: {item.computed_hash}")
        if item.current_hash:
            lines.append(f"  current:  {item.current_hash}")
        if show_snippets and item.cited_text is not None:
            lines.append("  cited text:")
            lines.extend(f"    {line}" for line in item.cited_text.splitlines() or [""])
    lines.append("Status: PASS" if report.ok() else "Status: FAIL")
    return "\n".join(lines)


def evidence(
    artifact: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to an existing antemortem JSON artifact.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    repo: Path = typer.Option(  # noqa: B008
        Path.cwd(),
        "--repo",
        "-r",
        help="Repository root to resolve cited files against.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    check: bool = typer.Option(  # noqa: B008
        False,
        "--check",
        help="Exit nonzero when hashes are missing, mismatched, oversized, or snippets do not match.",
    ),
    write_missing: bool = typer.Option(  # noqa: B008
        False,
        "--write-missing",
        help="Fill missing evidence_hash values when citation validation succeeds.",
    ),
    show_snippets: bool = typer.Option(  # noqa: B008
        False,
        "--show-snippets",
        help="Show normalized cited source text in the report.",
    ),
    json_output: bool = typer.Option(  # noqa: B008
        False,
        "--json",
        help="Print a stable JSON report.",
    ),
) -> None:
    """Inspect and recompute evidence hashes for an existing artifact."""
    try:
        report = inspect_evidence(artifact, repo, write_missing=write_missing)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        typer.secho(f"FAIL: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(json.dumps(report.as_json(show_snippets=show_snippets), indent=2, sort_keys=True))
    else:
        typer.echo(_render_text(report, show_snippets=show_snippets))

    if check and not report.ok():
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)
