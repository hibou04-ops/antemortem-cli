# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""`antemortem metrics` — fabricated-citation metrics for an artifact.

The headline "we catch the LLM hallucinating" number, standalone. Point
it at a ``<doc>.json`` run artifact and it reports how many cited
findings have evidence that actually resolves on disk (verified) versus
how many are fabricated (bad path, out-of-range line, or stale
evidence_hash). Unlike ``lint``, this command runs no schema/document
checks — it answers exactly one question: is the model citing real
evidence?

``--format json`` emits the stable machine-readable summary for CI;
``--fail-over`` lets a pipeline fail when the fabrication rate exceeds a
threshold (e.g. ``--fail-over 0`` = zero tolerance for hallucinated
citations).
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from antemortem.citation_metrics import metrics_from_artifact
from antemortem.exit_codes import POLICY_GATE_FAILURE, SUCCESS, USAGE_ERROR, VALIDATION_FAILURE


def _render_text(metrics, artifact: Path) -> str:
    lines = [
        f"Artifact: {artifact}",
        (
            "Citations: "
            f"verified={metrics.verified}, "
            f"fabricated={metrics.fabricated}, "
            f"unresolved={metrics.unresolved}, "
            f"cited={metrics.cited}, "
            f"total={metrics.total}"
        ),
        f"Fabrication rate: {metrics.fabrication_rate:.1%} of cited",
    ]
    for f in metrics.findings:
        if f.status == "unresolved":
            lines.append(f"- {f.kind} {f.id} ({f.label}): UNRESOLVED (no citation)")
            continue
        detail = f.status.upper()
        if f.reason:
            detail += f" — {f.reason}"
        lines.append(f"- {f.kind} {f.id} ({f.label}): {detail}  [{f.citation}]")
    lines.append("Status: PASS" if metrics.ok else "Status: FAIL (fabricated citations present)")
    return "\n".join(lines)


def metrics(
    artifact: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to an existing antemortem JSON artifact (<doc>.json).",
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
    output_format: str = typer.Option(  # noqa: B008
        "text",
        "--format",
        help="Output format: 'text' (default) or 'json' for CI.",
    ),
    fail_over: float | None = typer.Option(  # noqa: B008
        None,
        "--fail-over",
        help=(
            "Exit with the policy-gate failure code when the fabrication rate "
            "(fabricated/cited) exceeds this value. Use --fail-over 0 for zero "
            "tolerance. Omit to never fail on the rate (exit 0 unless the "
            "artifact is unreadable)."
        ),
        min=0.0,
        max=1.0,
    ),
) -> None:
    """Report verified vs fabricated citation counts for a run artifact."""
    fmt = output_format.lower().strip()
    if fmt not in ("text", "json"):
        typer.secho(
            f"FAIL: unknown --format {output_format!r}. "
            "Why: metrics can only render 'text' or 'json'. "
            f"Next: rerun `antemortem metrics {artifact} --format json`.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=USAGE_ERROR)

    try:
        result = metrics_from_artifact(artifact, repo)
    except ValueError as exc:
        typer.secho(
            f"FAIL: {exc}. "
            "Why: metrics needs a valid run artifact to inspect. "
            f"Next: regenerate it with `antemortem run` or inspect `{artifact}`.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=VALIDATION_FAILURE) from exc

    if fmt == "json":
        typer.echo(result.to_json_str())
    else:
        typer.echo(_render_text(result, artifact))

    if fail_over is not None and result.fabrication_rate > fail_over:
        typer.secho(
            f"FAIL: fabrication rate {result.fabrication_rate:.1%} exceeds "
            f"--fail-over {fail_over:.1%}. "
            "Why: CI policy rejects artifacts with hallucinated citations above "
            "the threshold. "
            "Next: fix the fabricated citations (see findings above) and re-run "
            "`antemortem run`.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=POLICY_GATE_FAILURE)
    raise typer.Exit(code=SUCCESS)
