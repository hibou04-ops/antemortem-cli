# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""`antemortem lint` -- schema and citation validation.

Two tiers of checks:

1. **Document schema**: YAML frontmatter parses, spec is non-empty, at least
   one trap row is present, and at least one file is listed under the Recon
   protocol. These apply to every antemortem document.
2. **Classification verification**: if a companion ``<doc>.json`` audit
   artifact exists (produced by ``antemortem run``), validate that every
   input trap has a classification, every citation parses, and every
   ``file:line`` points to an existing line within ``--repo``.

Exit 0 on pass, 1 on failure. Suitable for CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

import typer
from pydantic import ValidationError

from antemortem._versions import (
    KNOWN_TEMPLATE_LABELS,
    SUPPORTED_PARSER_CONTRACTS,
    SUPPORTED_SCHEMA_VERSIONS,
)
from antemortem.citations import (
    MAX_EVIDENCE_RANGE_LINES,
    compute_evidence_hash,
    compute_evidence_sha256,
    is_evidence_range_too_large,
    is_valid_evidence_hash,
    normalize_evidence_text,
    read_citation_text,
    verify_citation,
)
from antemortem.exit_codes import SUCCESS, VALIDATION_FAILURE
from antemortem.file_safety import resolve_repo_path
from antemortem.parser import (
    DocumentParseError,
    _find_section,
    _split_sections,
    parse_document,
    split_markdown_table_row,
)
from antemortem.schema import AntemortemDocument, AntemortemOutput


class LintResult(NamedTuple):
    """Outcome of a lint pass."""

    ok: bool
    violations: list[str]
    checked: int  # number of checks that ran (passed or failed)


def _lint_document(doc: AntemortemDocument, repo_root: Path) -> list[str]:
    """Pre-run schema checks that apply to every antemortem document."""
    violations: list[str] = []
    if not doc.spec.strip():
        violations.append("spec: '## 1. The change' section is empty or missing")
    if not doc.traps:
        violations.append("traps: no rows parsed from the pre-recon Traps table")
    if not doc.files_to_read:
        violations.append("files_to_read: no files listed under 'Recon protocol'")
    if duplicates := _duplicate_trap_ids(doc):
        violations.append(f"traps: duplicate trap ids: {', '.join(duplicates)}")
    if _trap_table_looks_malformed(doc):
        violations.append("traps: malformed table row in pre-recon Traps section")
    for rel_path in doc.files_to_read:
        resolution = resolve_repo_path(rel_path, repo_root)
        if not resolution.allowed:
            violations.append(f"files_to_read {rel_path}: {resolution.reason}")

    # Version contract — only fires when the field is present and unknown.
    # Missing fields are OK: pre-v0.7 documents pre-date the contract and
    # round-trip cleanly through the current parser.
    fm = doc.frontmatter
    if fm.parser_contract and fm.parser_contract not in SUPPORTED_PARSER_CONTRACTS:
        violations.append(
            f"frontmatter.parser_contract: unsupported value "
            f"{fm.parser_contract!r}. Supported: "
            f"{', '.join(sorted(SUPPORTED_PARSER_CONTRACTS))}. "
            "Re-scaffold with `antemortem init` or upgrade the binary."
        )
    if fm.schema_version and fm.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        violations.append(
            f"frontmatter.schema_version: unsupported value "
            f"{fm.schema_version!r}. Supported: "
            f"{', '.join(sorted(SUPPORTED_SCHEMA_VERSIONS))}."
        )
    if fm.template and fm.template not in KNOWN_TEMPLATE_LABELS:
        violations.append(
            f"frontmatter.template: unknown label {fm.template!r}. "
            f"Known: {', '.join(sorted(KNOWN_TEMPLATE_LABELS))}."
        )
    return violations


def _duplicate_trap_ids(doc: AntemortemDocument) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for trap in doc.traps:
        if trap.id in seen:
            duplicates.add(trap.id)
        seen.add(trap.id)
    return sorted(duplicates)


def _trap_table_looks_malformed(doc: AntemortemDocument) -> bool:
    sections = _split_sections(doc.raw_markdown)
    body = _find_section(sections, "trap")
    if not body:
        return False
    data_rows = []
    for raw in body.splitlines():
        stripped = raw.strip()
        if not stripped.startswith("|"):
            continue
        cells = split_markdown_table_row(stripped)
        if not cells:
            continue
        first = cells[0].strip().lower()
        if first in ("#", "id", "") or set(first) <= set("-: "):
            continue
        data_rows.append(cells)
    if not data_rows:
        return False
    return any(len(row) < 3 for row in data_rows)


def _lint_artifact(
    artifact_path: Path,
    doc: AntemortemDocument,
    repo_root: Path,
    *,
    strict_evidence: bool = False,
) -> list[str]:
    """Post-run checks that apply when a JSON audit artifact exists."""
    violations: list[str] = []
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{artifact_path.name}: invalid JSON -- {exc.msg} at line {exc.lineno}"]
    except OSError as exc:
        return [f"{artifact_path.name}: cannot read -- {exc}"]

    try:
        output = AntemortemOutput.model_validate(payload)
    except ValidationError as exc:
        return [f"{artifact_path.name}: schema validation failed -- {exc.error_count()} issues"]

    trap_ids = {t.id for t in doc.traps}
    classified_ids = {c.id for c in output.classifications}

    for missing in sorted(trap_ids - classified_ids):
        violations.append(f"classification: missing for trap {missing}")

    for c in output.classifications:
        if c.id not in trap_ids:
            violations.append(
                f"classification {c.id}: refers to a trap id not present in the input table"
            )
        if c.label == "UNRESOLVED":
            if c.citation is not None:
                violations.append(
                    f"classification {c.id}: UNRESOLVED must have citation=null (got {c.citation!r})"
                )
            continue
        if not c.citation:
            violations.append(f"classification {c.id}: citation is required for {c.label}")
            continue
        result = verify_citation(c.citation, repo_root)
        if not result.ok:
            violations.append(f"classification {c.id}: {result.reason}")
            continue
        if result.parsed is not None:
            violations.extend(
                _check_evidence_binding(
                    f"classification {c.id}",
                    result.parsed,
                    repo_root,
                    evidence_hash=c.evidence_hash,
                    legacy_sha256=c.evidence_sha256,
                    evidence_snippet=c.evidence_snippet,
                    strict_evidence=strict_evidence,
                )
            )

    for nt in output.new_traps:
        result = verify_citation(nt.citation, repo_root)
        if not result.ok:
            violations.append(f"new_trap {nt.id}: {result.reason}")
            continue
        if result.parsed is not None:
            violations.extend(
                _check_evidence_binding(
                    f"new_trap {nt.id}",
                    result.parsed,
                    repo_root,
                    evidence_hash=nt.evidence_hash,
                    legacy_sha256=nt.evidence_sha256,
                    evidence_snippet=nt.evidence_snippet,
                    strict_evidence=strict_evidence,
                )
            )

    return violations


def _check_evidence_binding(
    subject: str,
    parsed,
    repo_root: Path,
    *,
    evidence_hash: str | None,
    legacy_sha256: str | None,
    evidence_snippet: str | None,
    strict_evidence: bool,
) -> list[str]:
    """Validate optional evidence binding fields for one cited finding."""
    violations: list[str] = []
    has_binding = bool(evidence_hash or legacy_sha256 or evidence_snippet)

    if strict_evidence and not evidence_hash:
        violations.append(f"{subject}: missing evidence_hash")

    if strict_evidence or has_binding:
        if is_evidence_range_too_large(parsed):
            line_count = parsed.end - parsed.start + 1
            violations.append(
                f"{subject}: cited range too large "
                f"({line_count} lines; max {MAX_EVIDENCE_RANGE_LINES})"
            )

    text = read_citation_text(parsed, repo_root)
    if text is None:
        return violations

    if evidence_hash:
        actual = compute_evidence_hash(text)
        if not is_valid_evidence_hash(evidence_hash) or actual != evidence_hash:
            violations.append(
                f"{subject}: hash mismatch "
                f"(expected {evidence_hash[:19]}..., got {actual[:19]}...). "
                "Re-run `antemortem run` to refresh the artifact, then re-review."
            )
    elif legacy_sha256:
        actual_sha256 = compute_evidence_sha256(text)
        if actual_sha256 != legacy_sha256:
            violations.append(
                f"{subject}: hash mismatch "
                f"(expected sha256:{legacy_sha256[:12]}..., "
                f"got sha256:{actual_sha256[:12]}...). "
                "Re-run `antemortem run` to refresh the artifact, then re-review."
            )

    if evidence_snippet is not None:
        snippet = normalize_evidence_text(evidence_snippet)
        if not snippet or snippet not in text:
            violations.append(f"{subject}: snippet not found in cited range")

    return violations


def run_lint(
    document: Path,
    repo_root: Path,
    *,
    strict_evidence: bool = False,
) -> LintResult:
    """Programmatic lint entry point. Returns ``LintResult`` without exiting."""
    try:
        doc = parse_document(document)
    except DocumentParseError as exc:
        return LintResult(ok=False, violations=[f"document: {exc}"], checked=1)

    violations = _lint_document(doc, repo_root)

    artifact_path = document.with_suffix(".json")
    ran_artifact = artifact_path.exists()
    if ran_artifact:
        violations.extend(
            _lint_artifact(
                artifact_path,
                doc,
                repo_root,
                strict_evidence=strict_evidence,
            )
        )

    checked = 3 + (1 if ran_artifact else 0)  # spec, traps, files, (+ artifact)
    return LintResult(ok=len(violations) == 0, violations=violations, checked=checked)


def lint(
    document: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to the antemortem document to validate.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    repo: Path = typer.Option(  # noqa: B008
        Path.cwd(),
        "--repo",
        "-r",
        help="Repository root to resolve cited files against. Defaults to current directory.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    strict_evidence: bool = typer.Option(  # noqa: B008
        False,
        "--strict-evidence",
        help=(
            "Require evidence_hash for every non-UNRESOLVED classification "
            "and every new_trap. Recommended for CI."
        ),
    ),
) -> None:
    """Validate schema and verify file:line citations."""
    result = run_lint(document, repo, strict_evidence=strict_evidence)
    artifact_note = (
        " (schema + classifications)"
        if document.with_suffix(".json").exists()
        else " (schema only; no audit artifact)"
    )

    if result.ok:
        typer.secho(
            f"PASS -- {document.name} validates clean{artifact_note}",
            fg=typer.colors.GREEN,
        )
        raise typer.Exit(code=SUCCESS)

    typer.secho(f"FAIL: {document.name}{artifact_note}", fg=typer.colors.RED, err=True)
    for v in result.violations:
        typer.secho(f"  - {v}", fg=typer.colors.RED, err=True)
    typer.secho(
        "Why: lint is the disk verification step before gate; invalid schema, "
        "citations, or evidence bindings make the artifact unsafe to trust. "
        f"Next: inspect `{document}`"
        + (f" and `{document.with_suffix('.json')}`" if document.with_suffix(".json").exists() else "")
        + f", then rerun `antemortem lint {document} --repo {repo}`.",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=VALIDATION_FAILURE)
