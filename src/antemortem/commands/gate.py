# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""`antemortem gate` — single CI-safe ship gate.

Combines `lint` (schema + citation verification) with a decision-allowlist
check on the artifact. Exits non-zero if either:

  - lint fails (schema invalid, missing classifications, citation does
    not point to an existing line), OR
  - the artifact's `decision` value is not in the caller's `--allow` set.

Default allowlist: SAFE_TO_PROCEED, PROCEED_WITH_GUARDS.

Without this command, `lint pass` did not imply "ship-ready" — a
DO_NOT_PROCEED artifact with valid citations would lint clean. CI
pipelines had to parse the JSON themselves to enforce the gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from antemortem.citation_metrics import compute_citation_metrics
from antemortem.commands.lint import run_lint
from antemortem.decision import DECISION_LABELS as VALID_DECISIONS
from antemortem.exit_codes import (
    POLICY_GATE_FAILURE,
    SUCCESS,
    USAGE_ERROR,
    VALIDATION_FAILURE,
)
from antemortem.schema import AntemortemOutput

DEFAULT_ALLOWED = ("SAFE_TO_PROCEED", "PROCEED_WITH_GUARDS")


def _parse_allow(allow: str) -> tuple[set[str], list[str]]:
    """Parse comma-separated decision list. Returns (set, errors)."""
    raw = [v.strip() for v in allow.split(",") if v.strip()]
    unknown = [v for v in raw if v not in VALID_DECISIONS]
    return set(raw), unknown


def _citation_metrics_json(artifact_path: Path, repo: Path) -> dict | None:
    """Best-effort fabricated-citation metrics for the gate JSON summary.

    Returns None when the artifact is absent or unparseable — those
    conditions already drive the gate verdict, so the metrics block is
    informational only and never raises.
    """
    if not artifact_path.exists():
        return None
    try:
        output = AntemortemOutput.model_validate(
            json.loads(artifact_path.read_text(encoding="utf-8"))
        )
    except Exception:  # noqa: BLE001 — metrics are best-effort; verdict is authoritative.
        return None
    return compute_citation_metrics(output, repo).to_json()


def gate(
    document: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to the antemortem document to gate.",
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
    allow: str = typer.Option(
        ",".join(DEFAULT_ALLOWED),
        "--allow",
        help=(
            "Comma-separated decisions that are allowed to ship. "
            "Default: SAFE_TO_PROCEED,PROCEED_WITH_GUARDS. "
            f"Valid values: {', '.join(VALID_DECISIONS)}."
        ),
    ),
    require_artifact: bool = typer.Option(
        True,
        "--require-artifact/--no-require-artifact",
        help=(
            "Fail when no <doc>.json audit artifact is present (default). "
            "Use --no-require-artifact only for pre-run schema-only gating."
        ),
    ),
    output_format: str = typer.Option(  # noqa: B008
        "text",
        "--format",
        help=(
            "Output format. 'text' (default) is the human-readable verdict; "
            "'json' emits a machine-readable summary (verdict, decision, "
            "allowlist, and fabricated-citation metrics) for CI. Exit code "
            "is identical across formats."
        ),
    ),
) -> None:
    """Combined lint + decision-allowlist ship gate. Exits 0 only when
    the document lints clean AND its decision is in the allowlist."""
    fmt = output_format.lower().strip()
    if fmt not in ("text", "json"):
        typer.secho(
            f"FAIL: unknown --format {output_format!r}. "
            "Why: gate can only render 'text' or 'json'. "
            f"Next: rerun `antemortem gate {document} --format json`.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=USAGE_ERROR)

    artifact_path_for_json = document.with_suffix(".json")

    def _emit_and_exit(
        *,
        code: int,
        status: str,
        reason: str,
        decision: str | None = None,
    ) -> None:
        """In json mode, print the structured summary and exit with ``code``.

        In text mode this is a no-op (the caller already printed the
        human-readable lines); it just exits with the same code so the
        text contract is byte-identical to pre-feature behaviour.
        """
        if fmt == "json":
            summary = {
                "schema": "antemortem-gate-v1",
                "document": str(document),
                "repo": str(repo),
                "status": status,  # "pass" | "fail"
                "reason": reason,
                "decision": decision,
                "allowlist": sorted(allowed),
                "exit_code": code,
                "citation_metrics": _citation_metrics_json(
                    artifact_path_for_json, repo
                ),
            }
            typer.echo(json.dumps(summary, indent=2, sort_keys=True))
        raise typer.Exit(code=code)

    allowed, unknown = _parse_allow(allow)
    if unknown:
        if fmt == "text":
            typer.secho(
                f"FAIL: --allow contains unknown decision(s): {', '.join(unknown)}. "
                "Why: gate policy must use the canonical decision enum. "
                f"Valid: {', '.join(VALID_DECISIONS)}. "
                f"Next: rerun `antemortem gate {document} --repo {repo} "
                f"--allow {','.join(DEFAULT_ALLOWED)}`.",
                fg=typer.colors.RED,
                err=True,
            )
        _emit_and_exit(
            code=USAGE_ERROR,
            status="fail",
            reason=f"unknown decision(s) in --allow: {', '.join(unknown)}",
        )
    if not allowed:
        if fmt == "text":
            typer.secho(
                "FAIL: --allow is empty. "
                "Why: an empty allowlist means no decision can pass CI. "
                f"Next: rerun `antemortem gate {document} --repo {repo} "
                f"--allow {','.join(DEFAULT_ALLOWED)}`.",
                fg=typer.colors.RED,
                err=True,
            )
        _emit_and_exit(code=USAGE_ERROR, status="fail", reason="empty --allow allowlist")

    lint_result = run_lint(document, repo)
    if not lint_result.ok:
        if fmt == "text":
            typer.secho(f"FAIL: {document.name} did not pass lint.", fg=typer.colors.RED, err=True)
            for v in lint_result.violations:
                typer.secho(f"  - {v}", fg=typer.colors.RED, err=True)
            typer.secho(
                "Why: gate cannot apply decision policy until schema, citations, "
                "and evidence are valid. "
                f"Next: run `antemortem lint {document} --repo {repo}`.",
                fg=typer.colors.RED,
                err=True,
            )
        _emit_and_exit(
            code=VALIDATION_FAILURE,
            status="fail",
            reason="lint failed: " + "; ".join(lint_result.violations),
        )

    artifact_path = document.with_suffix(".json")
    if not artifact_path.exists():
        if require_artifact:
            if fmt == "text":
                typer.secho(
                    f"FAIL: {document.name} has no audit artifact ({artifact_path.name}). "
                    "Why: gate needs the run artifact's decision field to enforce policy. "
                    f"Next: run `antemortem run {document} --repo {repo}`, or pass "
                    "`--no-require-artifact` only for schema-only gating.",
                    fg=typer.colors.RED,
                    err=True,
                )
            _emit_and_exit(
                code=VALIDATION_FAILURE,
                status="fail",
                reason="no audit artifact present",
            )
        if fmt == "text":
            typer.secho(
                f"PASS -- {document.name} (lint only; no artifact)",
                fg=typer.colors.GREEN,
            )
        _emit_and_exit(
            code=SUCCESS,
            status="pass",
            reason="lint clean; no artifact required",
        )

    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        if fmt == "text":
            typer.secho(
                f"FAIL: {artifact_path.name} is invalid JSON ({exc.msg} at line {exc.lineno}). "
                "Why: gate cannot read a decision from a malformed artifact. "
                f"Next: inspect `{artifact_path}` or regenerate it with "
                f"`antemortem run {document} --repo {repo}`.",
                fg=typer.colors.RED,
                err=True,
            )
        _emit_and_exit(
            code=VALIDATION_FAILURE,
            status="fail",
            reason=f"artifact is invalid JSON: {exc.msg} at line {exc.lineno}",
        )

    decision = payload.get("decision")
    if decision is None:
        if fmt == "text":
            typer.secho(
                f"FAIL: {artifact_path.name} has no `decision` field. "
                "Why: gate can only enforce an allowlist against an explicit decision. "
                f"Next: rerun `antemortem run {document} --repo {repo}` without `--no-decision`.",
                fg=typer.colors.RED,
                err=True,
            )
        _emit_and_exit(
            code=VALIDATION_FAILURE,
            status="fail",
            reason="artifact has no `decision` field",
        )

    if decision not in allowed:
        if fmt == "text":
            typer.secho(
                f"FAIL: policy gate blocked {document.name}: decision={decision!r} "
                f"is not in allowlist ({', '.join(sorted(allowed))}). "
                "Why: CI policy only permits explicitly allowed decisions. "
                f"Next: inspect `{artifact_path}` decision_rationale, then either fix the "
                "finding or change `--allow` only if release policy changed.",
                fg=typer.colors.RED,
                err=True,
            )
            rationale = payload.get("decision_rationale")
            if rationale:
                typer.secho(f"  rationale: {rationale}", fg=typer.colors.RED, err=True)
        _emit_and_exit(
            code=POLICY_GATE_FAILURE,
            status="fail",
            reason=f"decision {decision!r} not in allowlist",
            decision=decision,
        )

    if fmt == "text":
        typer.secho(
            f"PASS -- {document.name}: decision={decision} (allowed)",
            fg=typer.colors.GREEN,
        )
    _emit_and_exit(
        code=SUCCESS,
        status="pass",
        reason=f"decision {decision} in allowlist",
        decision=decision,
    )
