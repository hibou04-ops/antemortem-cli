# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Recompute current evidence and decision before applying the CI allowlist.

A stored decision is an assertion to cross-check, never authorization.
Empty, fabricated or insufficient evidence cannot be admitted by --allow.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError

from antemortem.citation_metrics import DEFAULT_MIN_EFFECTIVE_COVERAGE, compute_citation_metrics
from antemortem.citations import CitationVerifier
from antemortem.commands.lint import run_lint
from antemortem.decision import DECISION_LABELS as VALID_DECISIONS
from antemortem.decision import DecisionPolicy, compute_decision
from antemortem.exit_codes import POLICY_GATE_FAILURE, SUCCESS, USAGE_ERROR, VALIDATION_FAILURE
from antemortem.schema import AntemortemOutput

DEFAULT_ALLOWED = ("SAFE_TO_PROCEED", "PROCEED_WITH_GUARDS")


def _parse_allow(allow: str) -> tuple[set[str], list[str]]:
    raw = [value.strip() for value in allow.split(",") if value.strip()]
    return set(raw), [value for value in raw if value not in VALID_DECISIONS]


def gate(
    document: Path = typer.Argument(  # noqa: B008
        ..., metavar="DOCUMENT", help="Path to the antemortem document to gate.",
        exists=True, file_okay=True, dir_okay=False, readable=True,
    ),
    repo: Path = typer.Option(  # noqa: B008
        Path.cwd(), "--repo", "-r", help="Repository root for disk citation checks.",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    allow: str = typer.Option(
        ",".join(DEFAULT_ALLOWED), "--allow",
        help="Allowed recomputed decisions; cannot override evidence or consistency failures.",
    ),
    require_artifact: bool = typer.Option(
        True, "--require-artifact/--no-require-artifact",
        help="Compatibility flag. Gate always requires evidence; use lint for schema-only checks.",
    ),
    output_format: str = typer.Option(
        "text", "--format", help="Output format: text or JSON. Exit policies are identical.",
    ),
    min_effective_coverage: float = typer.Option(
        DEFAULT_MIN_EFFECTIVE_COVERAGE, "--min-effective-coverage",
        min=DEFAULT_MIN_EFFECTIVE_COVERAGE, max=1.0,
        help="Minimum verified/total coverage; may strengthen the 0.8 floor, never weaken it.",
    ),
) -> None:
    """Validate current evidence and recompute the stored decision before CI approval."""
    fmt = output_format.lower().strip()
    if fmt not in ("text", "json"):
        typer.secho(
            f"FAIL: unknown --format {output_format!r}. Why: expected text or json. "
            "Next: rerun with --format json.", fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=USAGE_ERROR)

    allowed, unknown = _parse_allow(allow)
    verifier = CitationVerifier(repo)
    artifact_path = document.with_suffix(".json")
    output: AntemortemOutput | None = None
    stored_decision: str | None = None
    computed_decision: str | None = None
    current_metrics = None
    artifact_text: str | None = None

    def finish(code: int, reason: str) -> None:
        nonlocal current_metrics
        # Both output formats refresh disk evidence at the final boundary.
        if output is not None:
            current_metrics = compute_citation_metrics(
                output, repo, verifier=verifier,
                min_effective_coverage=min_effective_coverage,
            )
            if code == SUCCESS and not current_metrics.ok:
                code = POLICY_GATE_FAILURE
                reason = "citation evidence changed or no longer satisfies coverage policy"
        authorized = code == SUCCESS
        if authorized:
            try:
                unchanged = artifact_path.read_text(encoding="utf-8") == artifact_text
            except (OSError, UnicodeError):
                unchanged = False
            if not unchanged:
                code, authorized = VALIDATION_FAILURE, False
                reason = "artifact changed during verification; rerun against a stable snapshot"
        if fmt == "json":
            typer.echo(json.dumps({
                "schema": "antemortem-gate-v1",
                "document": str(document), "repo": str(repo),
                "status": "pass" if authorized else "fail", "reason": reason,
                "decision": computed_decision,
                "stored_decision": stored_decision,
                "computed_decision": computed_decision,
                "deployment_authorized": authorized,
                "allowlist": sorted(allowed), "exit_code": code,
                "citation_metrics": current_metrics.to_json() if current_metrics else None,
            }, indent=2, sort_keys=True))
        elif authorized:
            typer.secho(
                f"PASS -- {document.name}: decision={computed_decision} (recomputed, allowed)",
                fg=typer.colors.GREEN,
            )
        else:
            typer.secho(
                f"FAIL: {reason}. Why: CI requires current verified evidence and a "
                f"consistent decision. Next: rerun `antemortem run {document} --repo {repo}` "
                "or use `antemortem lint` for schema-only inspection.",
                fg=typer.colors.RED, err=True,
            )
        raise typer.Exit(code=code)

    if unknown:
        finish(USAGE_ERROR, f"--allow contains unknown decision(s): {', '.join(unknown)}")
    if not allowed:
        finish(USAGE_ERROR, "empty --allow allowlist")
    try:
        policy = DecisionPolicy(min_effective_coverage=min_effective_coverage)
    except ValueError as exc:
        finish(USAGE_ERROR, str(exc))

    # Parse classifications, ignoring all supplied metrics and counts.
    if artifact_path.exists():
        try:
            artifact_text = artifact_path.read_text(encoding="utf-8")
            output = AntemortemOutput.model_validate(json.loads(artifact_text))
        except (OSError, ValueError, ValidationError) as exc:
            finish(VALIDATION_FAILURE, f"artifact is unreadable or invalid: {type(exc).__name__}")
        stored_decision = output.decision

    lint_result = run_lint(document, repo, verifier=verifier)
    if not lint_result.ok:
        finish(VALIDATION_FAILURE, "lint failed: " + "; ".join(lint_result.violations))
    if output is None:
        finish(VALIDATION_FAILURE, "no audit artifact present; evidence cannot be recomputed")

    current_metrics = compute_citation_metrics(
        output, repo, verifier=verifier, min_effective_coverage=min_effective_coverage,
    )
    report = compute_decision(output, policy=policy, citation_metrics=current_metrics)
    computed_decision = report.decision
    if stored_decision is None:
        finish(VALIDATION_FAILURE, "artifact has no `decision` field")
    if not current_metrics.ok:
        finish(
            POLICY_GATE_FAILURE,
            "evidence policy failed: "
            f"verified={current_metrics.verified}, fabricated={current_metrics.fabricated}, "
            f"unresolved={current_metrics.unresolved}, total={current_metrics.total}; "
            f"effective_coverage={current_metrics.effective_coverage:.1%}, "
            f"minimum={min_effective_coverage:.1%}",
        )
    if stored_decision != computed_decision:
        finish(
            POLICY_GATE_FAILURE,
            f"stored decision {stored_decision!r} differs from recomputed {computed_decision!r}",
        )
    if computed_decision not in allowed:
        finish(POLICY_GATE_FAILURE, f"decision {computed_decision!r} not in allowlist")
    finish(SUCCESS, f"recomputed decision {computed_decision} in allowlist")
