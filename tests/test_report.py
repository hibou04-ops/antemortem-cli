"""Tests for the `antemortem report` scorecard command."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from antemortem.cli import app
from antemortem.commands.report import build_report

runner = CliRunner()


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "auth.py").write_text(
        "\n".join(f"auth line {i}" for i in range(1, 21)) + "\n",
        encoding="utf-8",
    )
    return repo


def _write_artifact(tmp_path: Path, *, decision: str = "PROCEED_WITH_GUARDS") -> Path:
    artifact = tmp_path / "feat.json"
    artifact.write_text(
        json.dumps(
            {
                "classifications": [
                    {"id": "t1", "label": "REAL", "citation": "src/auth.py:5",
                     "note": "real risk", "severity": "high",
                     "remediation": "add a guard"},
                    {"id": "t2", "label": "GHOST", "citation": "src/auth.py:10",
                     "note": "already handled"},
                    {"id": "t3", "label": "UNRESOLVED", "citation": None,
                     "note": "no evidence"},
                ],
                "new_traps": [
                    {"id": "t_new_1", "hypothesis": "logging gap",
                     "citation": "src/auth.py:15", "note": "no audit line"},
                ],
                "spec_mutations": ["Add audit logging requirement."],
                "decision": decision,
                "decision_rationale": "One REAL with remediation; proceed with guards.",
            }
        ),
        encoding="utf-8",
    )
    return artifact


def test_report_markdown_contains_decision_and_table(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(tmp_path)
    md = build_report(artifact, repo, output_format="markdown")
    assert "Antemortem scorecard" in md
    assert "PROCEED_WITH_GUARDS" in md
    assert "| t1 |" in md and "REAL" in md
    assert "t_new_1" in md
    assert "Add audit logging requirement." in md
    # Citation verification section reports verified count (3 cited, all valid).
    assert "Verified: **3**" in md
    assert "Fabricated: **0**" in md


def test_report_markdown_flags_fabricated_citation(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = tmp_path / "feat.json"
    artifact.write_text(
        json.dumps(
            {
                "classifications": [
                    {"id": "t1", "label": "REAL", "citation": "src/ghost.py:5", "note": "n"},
                ],
                "new_traps": [],
                "spec_mutations": [],
                "decision": "NEEDS_MORE_EVIDENCE",
                "decision_rationale": "bad citation",
            }
        ),
        encoding="utf-8",
    )
    md = build_report(artifact, repo, output_format="markdown")
    assert "Fabricated: **1**" in md
    assert "fabricated" in md  # status column


def test_report_html_is_self_contained(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(tmp_path)
    html_out = build_report(artifact, repo, output_format="html")
    assert html_out.startswith("<!doctype html>")
    assert "<style>" in html_out  # inlined CSS, no external assets
    assert "http://" not in html_out and "https://" not in html_out  # no remote refs
    assert "PROCEED_WITH_GUARDS" in html_out
    assert "<table>" in html_out


def test_report_html_escapes_content(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = tmp_path / "feat.json"
    artifact.write_text(
        json.dumps(
            {
                "classifications": [
                    {"id": "t1", "label": "REAL", "citation": "src/auth.py:5",
                     "note": "<script>alert(1)</script> & more"},
                ],
                "new_traps": [],
                "spec_mutations": [],
                "decision": "PROCEED_WITH_GUARDS",
                "decision_rationale": "x",
            }
        ),
        encoding="utf-8",
    )
    html_out = build_report(artifact, repo, output_format="html")
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_report_deterministic(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(tmp_path)
    a = build_report(artifact, repo, output_format="markdown")
    b = build_report(artifact, repo, output_format="markdown")
    assert a == b
    ha = build_report(artifact, repo, output_format="html")
    hb = build_report(artifact, repo, output_format="html")
    assert ha == hb


def test_report_command_stdout(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(tmp_path)
    result = runner.invoke(app, ["report", str(artifact), "--repo", str(repo)])
    assert result.exit_code == 0, result.stdout
    assert "Antemortem scorecard" in result.stdout


def test_report_command_writes_file(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(tmp_path)
    out = tmp_path / "scorecard.html"
    result = runner.invoke(
        app,
        ["report", str(artifact), "--repo", str(repo), "--format", "html", "--out", str(out)],
    )
    assert result.exit_code == 0
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert "Report written" in result.stdout


def test_report_command_rejects_bad_format(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(tmp_path)
    result = runner.invoke(
        app, ["report", str(artifact), "--repo", str(repo), "--format", "pdf"]
    )
    assert result.exit_code == 2


def test_report_command_fails_on_malformed_artifact(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = tmp_path / "bad.json"
    artifact.write_text("{not json", encoding="utf-8")
    result = runner.invoke(app, ["report", str(artifact), "--repo", str(repo)])
    assert result.exit_code == 1
    assert "FAIL" in result.stderr


def test_report_title_override(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(tmp_path)
    md = build_report(artifact, repo, output_format="markdown", title="My Change")
    assert "My Change" in md
