"""Tests for the `--format json` option on lint and gate."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from antemortem.cli import app

runner = CliRunner()


_DOC = """---
name: feat
date: 2026-04-21
template: basic
---

# Antemortem — feat

## 1. The change

Refactor the auth flow.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | token expiry | trap | 60% | from incident |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/auth.py`
"""


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "auth.py").write_text(
        "\n".join(f"auth line {i}" for i in range(1, 21)) + "\n",
        encoding="utf-8",
    )
    return repo


def _setup(tmp_path: Path, classifications: list[dict], *, decision: str | None = None) -> tuple[Path, Path]:
    doc = tmp_path / "feat.md"
    doc.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)
    artifact: dict = {
        "classifications": classifications,
        "new_traps": [],
        "spec_mutations": [],
    }
    if decision is not None:
        artifact["decision"] = decision
        artifact["decision_rationale"] = "test"
    doc.with_suffix(".json").write_text(json.dumps(artifact), encoding="utf-8")
    return doc, repo


# --------------------------- lint --format json ---------------------------


def test_lint_json_pass(tmp_path: Path):
    doc, repo = _setup(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/auth.py:5", "note": "n"}],
    )
    result = runner.invoke(app, ["lint", str(doc), "--repo", str(repo), "--format", "json"])
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["schema"] == "antemortem-lint-v1"
    assert data["ok"] is True
    assert data["artifact_present"] is True
    assert data["citation_metrics"]["verified"] == 1
    assert data["citation_metrics"]["fabricated"] == 0


def test_lint_json_reports_fabricated_metrics_even_when_schema_ok(tmp_path: Path):
    # Citation points to a file that does not exist → lint violation AND
    # the metrics block reports it as fabricated.
    doc, repo = _setup(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/ghost.py:5", "note": "n"}],
    )
    result = runner.invoke(app, ["lint", str(doc), "--repo", str(repo), "--format", "json"])
    assert result.exit_code == 1  # lint failed (bad citation)
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert data["citation_metrics"]["fabricated"] == 1


def test_lint_json_schema_only_no_artifact(tmp_path: Path):
    doc = tmp_path / "feat.md"
    doc.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["lint", str(doc), "--repo", str(repo), "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["artifact_present"] is False
    assert data["citation_metrics"] is None


def test_lint_rejects_bad_format(tmp_path: Path):
    doc, repo = _setup(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/auth.py:5", "note": "n"}],
    )
    result = runner.invoke(app, ["lint", str(doc), "--repo", str(repo), "--format", "yaml"])
    assert result.exit_code == 2


# --------------------------- gate --format json ---------------------------


def test_gate_json_pass(tmp_path: Path):
    doc, repo = _setup(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/auth.py:5", "note": "n"}],
        decision="PROCEED_WITH_GUARDS",
    )
    result = runner.invoke(app, ["gate", str(doc), "--repo", str(repo), "--format", "json"])
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["schema"] == "antemortem-gate-v1"
    assert data["status"] == "pass"
    assert data["decision"] == "PROCEED_WITH_GUARDS"
    assert data["citation_metrics"]["verified"] == 1


def test_gate_json_blocked_decision(tmp_path: Path):
    doc, repo = _setup(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/auth.py:5", "note": "n"}],
        decision="DO_NOT_PROCEED",
    )
    result = runner.invoke(app, ["gate", str(doc), "--repo", str(repo), "--format", "json"])
    assert result.exit_code == 4  # POLICY_GATE_FAILURE
    data = json.loads(result.stdout)
    assert data["status"] == "fail"
    assert data["decision"] == "DO_NOT_PROCEED"
    assert data["exit_code"] == 4


def test_gate_json_lint_failure(tmp_path: Path):
    doc, repo = _setup(
        tmp_path,
        [{"id": "1", "label": "REAL", "citation": "src/auth.py:9999", "note": "n"}],
        decision="SAFE_TO_PROCEED",
    )
    result = runner.invoke(app, ["gate", str(doc), "--repo", str(repo), "--format", "json"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail"
    assert "lint failed" in data["reason"]


def test_gate_json_no_artifact(tmp_path: Path):
    doc = tmp_path / "feat.md"
    doc.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["gate", str(doc), "--repo", str(repo), "--format", "json"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail"
    assert data["citation_metrics"] is None


def test_gate_rejects_bad_format(tmp_path: Path):
    doc, repo = _setup(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/auth.py:5", "note": "n"}],
        decision="SAFE_TO_PROCEED",
    )
    result = runner.invoke(app, ["gate", str(doc), "--repo", str(repo), "--format", "yaml"])
    assert result.exit_code == 2


def test_gate_text_output_unchanged(tmp_path: Path):
    """Default text format must stay byte-compatible (no JSON leak)."""
    doc, repo = _setup(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/auth.py:5", "note": "n"}],
        decision="PROCEED_WITH_GUARDS",
    )
    result = runner.invoke(app, ["gate", str(doc), "--repo", str(repo)])
    assert result.exit_code == 0
    assert "PASS" in result.stdout
    assert "{" not in result.stdout  # no JSON in text mode
