# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Tests for the `antemortem gate` command — lint + decision allowlist."""

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
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text(
        "\n".join(f"auth line {i}" for i in range(1, 21)) + "\n",
        encoding="utf-8",
    )
    return repo


def _setup(tmp_path: Path, decision: str) -> tuple[Path, Path]:
    """Write a doc + matching artifact with the given decision."""
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)
    artifact = {
        "classifications": [
            {"id": "t1", "label": "REAL", "citation": "src/auth.py:5", "note": "n"},
        ],
        "new_traps": [],
        "spec_mutations": [],
        "decision": decision,
        "decision_rationale": "test",
    }
    doc_path.with_suffix(".json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    return doc_path, repo


def test_gate_passes_when_decision_in_default_allowlist(tmp_path: Path):
    doc_path, repo = _setup(tmp_path, "PROCEED_WITH_GUARDS")
    result = runner.invoke(app, ["gate", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 0, result.stdout
    assert "PASS" in result.stdout
    assert "PROCEED_WITH_GUARDS" in result.stdout


def test_gate_fails_when_decision_blocks_ship(tmp_path: Path):
    doc_path, repo = _setup(tmp_path, "DO_NOT_PROCEED")
    result = runner.invoke(app, ["gate", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 4
    assert "DO_NOT_PROCEED" in result.stderr
    assert "FAIL" in result.stderr
    assert "Why:" in result.stderr
    assert "Next:" in result.stderr


def test_gate_fails_when_needs_more_evidence(tmp_path: Path):
    """NEEDS_MORE_EVIDENCE is not in default allowlist."""
    doc_path, repo = _setup(tmp_path, "NEEDS_MORE_EVIDENCE")
    result = runner.invoke(app, ["gate", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 4


def test_gate_custom_allowlist(tmp_path: Path):
    """User can broaden or restrict the allowlist."""
    doc_path, repo = _setup(tmp_path, "NEEDS_MORE_EVIDENCE")
    # Explicitly allow NEEDS_MORE_EVIDENCE.
    result = runner.invoke(
        app,
        [
            "gate",
            str(doc_path),
            "--repo",
            str(repo),
            "--allow",
            "SAFE_TO_PROCEED,NEEDS_MORE_EVIDENCE",
        ],
    )
    assert result.exit_code == 0


def test_gate_strict_only_safe(tmp_path: Path):
    """Restrict to SAFE_TO_PROCEED only — PROCEED_WITH_GUARDS is rejected."""
    doc_path, repo = _setup(tmp_path, "PROCEED_WITH_GUARDS")
    result = runner.invoke(
        app,
        ["gate", str(doc_path), "--repo", str(repo), "--allow", "SAFE_TO_PROCEED"],
    )
    assert result.exit_code == 4


def test_gate_rejects_unknown_decision_in_allow(tmp_path: Path):
    doc_path, repo = _setup(tmp_path, "SAFE_TO_PROCEED")
    result = runner.invoke(
        app,
        ["gate", str(doc_path), "--repo", str(repo), "--allow", "MAYBE_OK"],
    )
    assert result.exit_code == 2
    assert "MAYBE_OK" in result.stderr


def test_gate_rejects_empty_allow(tmp_path: Path):
    doc_path, repo = _setup(tmp_path, "SAFE_TO_PROCEED")
    result = runner.invoke(
        app, ["gate", str(doc_path), "--repo", str(repo), "--allow", ""]
    )
    assert result.exit_code == 2


def test_gate_fails_when_lint_fails(tmp_path: Path):
    """Bad citation in artifact → lint fails → gate fails."""
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)
    artifact = {
        "classifications": [
            {"id": "1", "label": "REAL", "citation": "src/auth.py:9999", "note": "n"},
        ],
        "new_traps": [],
        "spec_mutations": [],
        "decision": "SAFE_TO_PROCEED",
    }
    doc_path.with_suffix(".json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    result = runner.invoke(app, ["gate", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 1
    assert "lint" in result.stderr.lower()


def test_gate_requires_artifact_by_default(tmp_path: Path):
    """No <doc>.json present → gate fails (default require-artifact=True)."""
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["gate", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 1
    assert "no audit artifact" in result.stderr


def test_gate_no_require_artifact_passes_when_lint_clean(tmp_path: Path):
    """--no-require-artifact lets schema-only gating pass before run."""
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)
    result = runner.invoke(
        app,
        ["gate", str(doc_path), "--repo", str(repo), "--no-require-artifact"],
    )
    assert result.exit_code == 0
    assert "lint only" in result.stdout


def test_gate_fails_on_artifact_without_decision_field(tmp_path: Path):
    """Artifact written with --no-decision lacks the field — gate must fail."""
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)
    artifact = {
        "classifications": [
            {"id": "t1", "label": "REAL", "citation": "src/auth.py:5", "note": "n"},
        ],
        "new_traps": [],
        "spec_mutations": [],
    }
    doc_path.with_suffix(".json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    result = runner.invoke(app, ["gate", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 1
    assert "no `decision` field" in result.stderr
