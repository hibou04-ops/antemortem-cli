# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""`antemortem report` — render a run artifact into a shareable scorecard.

Takes a ``<doc>.json`` audit artifact (the output of ``antemortem run``)
and renders a single-file Markdown or HTML scorecard: the decision
verdict, a per-trap REAL / GHOST / NEW / UNRESOLVED table, the
fabricated-citation verification status, and the decision rationale. The
report is self-contained (HTML inlines its own CSS — no external assets)
so it can be attached to a PR, emailed, or published as a CI artifact.

Stdlib only — no templating engine. Determinism: identical artifact +
repo inputs produce byte-identical output (no timestamps injected unless
the artifact already carries one in ``run_metadata``).
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path

import typer
from pydantic import ValidationError

from antemortem.citation_metrics import CitationMetrics, compute_citation_metrics
from antemortem.exit_codes import SUCCESS, USAGE_ERROR, VALIDATION_FAILURE
from antemortem.schema import AntemortemOutput


@dataclass(frozen=True)
class ReportRow:
    """One finding row in the scorecard table."""

    id: str
    kind: str  # "trap" | "new"
    label: str
    citation: str
    citation_status: str  # "verified" | "fabricated" | "unresolved"
    severity: str
    note: str


def _rows(output: AntemortemOutput, metrics: CitationMetrics) -> list[ReportRow]:
    """Build the per-finding table rows, joining labels with citation status."""
    status_by_key: dict[tuple[str, str], str] = {
        (f.kind, f.id): f.status for f in metrics.findings
    }
    rows: list[ReportRow] = []
    for c in output.classifications:
        rows.append(
            ReportRow(
                id=c.id,
                kind="trap",
                label=c.label,
                citation=c.citation or "—",
                citation_status=status_by_key.get(("classification", c.id), "unresolved"),
                severity=c.severity or "—",
                note=c.note or "",
            )
        )
    for nt in output.new_traps:
        rows.append(
            ReportRow(
                id=nt.id,
                kind="new",
                label=nt.label,
                citation=nt.citation,
                citation_status=status_by_key.get(("new_trap", nt.id), "unresolved"),
                severity=nt.severity or "—",
                note=nt.note or "",
            )
        )
    return rows


def render_markdown(
    output: AntemortemOutput,
    metrics: CitationMetrics,
    *,
    title: str,
) -> str:
    """Render the scorecard as Markdown."""
    decision = output.decision or "—"
    rows = _rows(output, metrics)
    lines: list[str] = [
        f"# Antemortem scorecard — {title}",
        "",
        f"**Decision:** `{decision}`",
        "",
    ]
    if output.decision_rationale:
        lines += [f"> {output.decision_rationale}", ""]

    lines += [
        "## Citation verification",
        "",
        f"- Verified: **{metrics.verified}**",
        f"- Fabricated: **{metrics.fabricated}**",
        f"- Unresolved (no claim): {metrics.unresolved}",
        f"- Fabrication rate: {metrics.fabrication_rate:.1%} of {metrics.cited} cited",
        "",
        "## Findings",
        "",
        "| id | kind | label | severity | citation | citation status | note |",
        "|----|------|-------|----------|----------|-----------------|------|",
    ]
    for r in rows:
        note = r.note.replace("|", r"\|").replace("\n", " ")
        citation = r.citation.replace("|", r"\|")
        lines.append(
            f"| {r.id} | {r.kind} | {r.label} | {r.severity} | "
            f"`{citation}` | {r.citation_status} | {note} |"
        )
    if output.spec_mutations:
        lines += ["", "## Spec mutations", ""]
        lines += [f"- {m}" for m in output.spec_mutations]
    lines.append("")
    return "\n".join(lines)


_LABEL_HINT = {
    "REAL": "real",
    "GHOST": "ghost",
    "NEW": "new",
    "UNRESOLVED": "unresolved",
}
_STATUS_HINT = {
    "verified": "ok",
    "fabricated": "bad",
    "unresolved": "muted",
}

_HTML_CSS = """\
:root { color-scheme: light dark; }
body { font: 15px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
       max-width: 920px; margin: 2rem auto; padding: 0 1rem; }
h1 { font-size: 1.5rem; } h2 { font-size: 1.15rem; margin-top: 1.6rem; }
.decision { display: inline-block; padding: .3rem .7rem; border-radius: 6px;
            font-weight: 700; }
.SAFE_TO_PROCEED { background: #1b5e20; color: #fff; }
.PROCEED_WITH_GUARDS { background: #b26a00; color: #fff; }
.NEEDS_MORE_EVIDENCE { background: #5d4037; color: #fff; }
.DO_NOT_PROCEED { background: #b71c1c; color: #fff; }
blockquote { border-left: 3px solid #888; margin: .6rem 0; padding: .2rem .9rem;
             color: #555; }
table { border-collapse: collapse; width: 100%; margin: .6rem 0; }
th, td { border: 1px solid #ccc; padding: .35rem .55rem; text-align: left;
         vertical-align: top; font-size: .92rem; }
th { background: rgba(127,127,127,.12); }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .88em; }
.label { font-weight: 700; }
.real { color: #c62828; } .ghost { color: #2e7d32; }
.new { color: #1565c0; } .unresolved { color: #6d4c41; }
.ok { color: #2e7d32; } .bad { color: #c62828; font-weight: 700; }
.muted { color: #999; }
.metrics { display: flex; gap: 1.2rem; flex-wrap: wrap; margin: .6rem 0; }
.metric { background: rgba(127,127,127,.10); border-radius: 6px; padding: .5rem .8rem; }
.metric .n { font-size: 1.4rem; font-weight: 700; display: block; }
"""


def render_html(
    output: AntemortemOutput,
    metrics: CitationMetrics,
    *,
    title: str,
) -> str:
    """Render the scorecard as a self-contained HTML document (inlined CSS)."""
    decision = output.decision or "—"
    decision_class = decision if decision in (
        "SAFE_TO_PROCEED",
        "PROCEED_WITH_GUARDS",
        "NEEDS_MORE_EVIDENCE",
        "DO_NOT_PROCEED",
    ) else ""
    esc = html.escape
    rows = _rows(output, metrics)

    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Antemortem scorecard — {esc(title)}</title>",
        f"<style>{_HTML_CSS}</style></head><body>",
        f"<h1>Antemortem scorecard — {esc(title)}</h1>",
        f'<p>Decision: <span class="decision {decision_class}">{esc(decision)}</span></p>',
    ]
    if output.decision_rationale:
        parts.append(f"<blockquote>{esc(output.decision_rationale)}</blockquote>")

    parts += [
        "<h2>Citation verification</h2>",
        '<div class="metrics">',
        f'<div class="metric"><span class="n ok">{metrics.verified}</span>verified</div>',
        f'<div class="metric"><span class="n bad">{metrics.fabricated}</span>fabricated</div>',
        f'<div class="metric"><span class="n muted">{metrics.unresolved}</span>unresolved</div>',
        f'<div class="metric"><span class="n">{metrics.fabrication_rate:.1%}</span>'
        f"fabrication rate ({metrics.cited} cited)</div>",
        "</div>",
        "<h2>Findings</h2>",
        "<table><thead><tr>"
        "<th>id</th><th>kind</th><th>label</th><th>severity</th>"
        "<th>citation</th><th>citation status</th><th>note</th>"
        "</tr></thead><tbody>",
    ]
    for r in rows:
        label_cls = _LABEL_HINT.get(r.label, "")
        status_cls = _STATUS_HINT.get(r.citation_status, "muted")
        parts.append(
            "<tr>"
            f"<td><code>{esc(r.id)}</code></td>"
            f"<td>{esc(r.kind)}</td>"
            f'<td class="label {label_cls}">{esc(r.label)}</td>'
            f"<td>{esc(r.severity)}</td>"
            f"<td><code>{esc(r.citation)}</code></td>"
            f'<td class="{status_cls}">{esc(r.citation_status)}</td>'
            f"<td>{esc(r.note)}</td>"
            "</tr>"
        )
    parts.append("</tbody></table>")

    if output.spec_mutations:
        parts.append("<h2>Spec mutations</h2><ul>")
        parts += [f"<li>{esc(m)}</li>" for m in output.spec_mutations]
        parts.append("</ul>")

    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def build_report(
    artifact_path: Path,
    repo_root: Path,
    *,
    output_format: str,
    title: str | None = None,
) -> str:
    """Load an artifact and render its scorecard in the requested format.

    Raises ``ValueError`` on a missing / malformed / schema-invalid
    artifact, mirroring the ``evidence`` and ``metrics`` failure contract.
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

    metrics = compute_citation_metrics(output, repo_root)
    report_title = title or artifact_path.stem
    if output_format == "html":
        return render_html(output, metrics, title=report_title)
    return render_markdown(output, metrics, title=report_title)


def report(
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
        help="Repository root to resolve cited files against for citation verification.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    output_format: str = typer.Option(  # noqa: B008
        "markdown",
        "--format",
        help="Scorecard format: 'markdown' (default) or 'html'. Both are single-file and self-contained.",
    ),
    out: Path | None = typer.Option(  # noqa: B008
        None,
        "--out",
        "-o",
        help="Write the report to this file instead of stdout.",
    ),
    title: str | None = typer.Option(  # noqa: B008
        None,
        "--title",
        help="Override the report title. Defaults to the artifact filename stem.",
    ),
) -> None:
    """Render a shareable scorecard (markdown/HTML) from a run artifact."""
    fmt = output_format.lower().strip()
    if fmt not in ("markdown", "md", "html"):
        typer.secho(
            f"FAIL: unknown --format {output_format!r}. "
            "Why: report can only render 'markdown' or 'html'. "
            f"Next: rerun `antemortem report {artifact} --format html`.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=USAGE_ERROR)
    fmt = "markdown" if fmt == "md" else fmt

    try:
        rendered = build_report(artifact, repo, output_format=fmt, title=title)
    except ValueError as exc:
        typer.secho(
            f"FAIL: {exc}. "
            "Why: report needs a valid run artifact to render. "
            f"Next: regenerate it with `antemortem run` or inspect `{artifact}`.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=VALIDATION_FAILURE) from exc

    if out is not None:
        out.write_text(rendered, encoding="utf-8")
        typer.secho(f"Report written: {out}", fg=typer.colors.GREEN)
    else:
        typer.echo(rendered)
    raise typer.Exit(code=SUCCESS)
