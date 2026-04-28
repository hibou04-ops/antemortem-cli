# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""`antemortem lint` ??schema and citation validation.

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

from antemortem.citations import verify_citation
from antemortem.parser import DocumentParseError, parse_document
from antemortem.schema import AntemortemDocument, AntemortemOutput


class LintResult(NamedTuple):
    """Outcome of a lint pass."""

    ok: bool
    violations: list[str]
    checked: int  # number of checks that ran (passed or failed)


def _lint_document(doc: AntemortemDocument) -> list[str]:
    """Pre-run schema checks that apply to every antemortem document."""
    violations: list[str] = []
    if not doc.spec.strip():
        violations.append("spec: '## 1. The change' section is empty or missing")
    if not doc.traps:
        violations.append("traps: no rows parsed from the pre-recon Traps table")
    if not doc.files_to_read:
        violations.append("files_to_read: no files listed under 'Recon protocol'")
    return violations


def _lint_artifact(
    artifact_path: Path,
    doc: AntemortemDocument,
    repo_root: Path,
) -> list[str]:
    """Post-run checks that apply when a JSON audit artifact exists."""
    violations: list[str] = []
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{artifact_path.name}: invalid JSON ??{exc.msg} at line {exc.lineno}"]
    except OSError as exc:
        return [f"{artifact_path.name}: cannot read ??{exc}"]

    try:
        output = AntemortemOutput.model_validate(payload)
    except ValidationError as exc:
        return [f"{artifact_path.name}: schema validation failed ??{exc.error_count()} issues"]

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

    for nt in output.new_traps:
        result = verify_citation(nt.citation, repo_root)
        if not result.ok:
            violations.append(f"new_trap {nt.id}: {result.reason}")

    return violations


def run_lint(
    document: Path,
    repo_root: Path,
) -> LintResult:
    """Programmatic lint entry point. Returns ``LintResult`` without exiting."""
    try:
        doc = parse_document(document)
    except DocumentParseError as exc:
        return LintResult(ok=False, violations=[f"document: {exc}"], checked=1)

    violations = _lint_document(doc)

    artifact_path = document.with_suffix(".json")
    ran_artifact = artifact_path.exists()
    if ran_artifact:
        violations.extend(_lint_artifact(artifact_path, doc, repo_root))

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
) -> None:
    """Validate schema and verify file:line citations."""
    result = run_lint(document, repo)
    artifact_note = (
        " (schema + classifications)"
        if document.with_suffix(".json").exists()
        else " (schema only; no audit artifact)"
    )

    if result.ok:
        typer.secho(
            f"PASS ??{document.name} validates clean{artifact_note}",
            fg=typer.colors.GREEN,
        )
        raise typer.Exit(code=0)

    typer.secho(f"FAIL ??{document.name}{artifact_note}", fg=typer.colors.RED, err=True)
    for v in result.violations:
        typer.secho(f"  - {v}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)
