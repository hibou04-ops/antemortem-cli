# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Tests for the evidence_sha256 stale-citation gate.

`run` stamps every cited classification with a SHA-256 of the cited text
at artifact-write time. `lint` recomputes that hash later and flags
mismatches as stale evidence — caught when code changes between the
recon run and CI verification.

Out of scope (documented limit): the hash detects line-content drift,
NOT semantic entailment. A line that still says "if user.is_admin:" but
no longer represents the risk the model claimed will pass this check.
That is an LLM/human concern.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from antemortem.citations import (
    compute_evidence_sha256,
    evidence_sha256_for_citation,
    parse_citation,
    read_citation_text,
)
from antemortem.cli import app
from antemortem.schema import AntemortemOutput, Classification, NewTrap

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper unit tests.
# ---------------------------------------------------------------------------


def test_read_citation_text_returns_exact_lines(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("a\nb\nc\nd\n", encoding="utf-8")
    parsed = parse_citation("x.py:2-3")
    assert parsed is not None
    text = read_citation_text(parsed, tmp_path)
    assert text == "b\nc\n"


def test_read_citation_text_returns_none_for_missing_file(tmp_path: Path):
    parsed = parse_citation("missing.py:1")
    assert parsed is not None
    assert read_citation_text(parsed, tmp_path) is None


def test_read_citation_text_returns_none_when_line_out_of_range(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("only one line\n", encoding="utf-8")
    parsed = parse_citation("x.py:5")
    assert parsed is not None
    assert read_citation_text(parsed, tmp_path) is None


def test_compute_evidence_sha256_is_stable():
    text = "if user.is_admin:\n    return True\n"
    assert compute_evidence_sha256(text) == compute_evidence_sha256(text)
    # Sanity: known SHA-256 prefix doesn't change between Python runs
    digest = compute_evidence_sha256(text)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_evidence_sha256_for_citation_end_to_end(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("line1\nline2\nline3\n", encoding="utf-8")
    digest = evidence_sha256_for_citation("x.py:2", tmp_path)
    assert digest is not None
    assert digest == compute_evidence_sha256("line2\n")


def test_evidence_sha256_for_citation_returns_none_on_failure(tmp_path: Path):
    assert evidence_sha256_for_citation("nonexistent.py:1", tmp_path) is None
    assert evidence_sha256_for_citation("not a citation", tmp_path) is None


# ---------------------------------------------------------------------------
# Run integration: artifact gets evidence_sha256 stamped.
# ---------------------------------------------------------------------------


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
| 2 | unresolvable | worry | 30% | not in code |

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


def _fake_provider(output, usage):
    provider = MagicMock()
    provider.name = "anthropic"
    provider.model = "mock-model"
    provider.structured_complete.return_value = (output, usage)
    return provider


def test_run_stamps_evidence_sha256_on_cited_classifications(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
            Classification(id="t2", label="UNRESOLVED", citation=None, note="n"),
        ],
    )
    fake = _fake_provider(output, {"input_tokens": 1, "output_tokens": 1})
    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 0, result.stdout

    payload = json.loads(doc_path.with_suffix(".json").read_text(encoding="utf-8"))
    cls_by_id = {c["id"]: c for c in payload["classifications"]}

    # Cited classification gets stamped.
    assert cls_by_id["t1"]["evidence_sha256"] is not None
    assert len(cls_by_id["t1"]["evidence_sha256"]) == 64

    # UNRESOLVED has no citation, so no hash.
    assert cls_by_id["t2"].get("evidence_sha256") is None


def test_run_stamps_evidence_sha256_on_new_traps(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
            Classification(id="t2", label="UNRESOLVED", citation=None, note="n"),
        ],
        new_traps=[
            NewTrap(
                id="t_new_1",
                hypothesis="logging gap",
                citation="src/auth.py:7",
                note="found",
            ),
        ],
    )
    fake = _fake_provider(output, {"input_tokens": 1, "output_tokens": 1})
    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 0, result.stdout

    payload = json.loads(doc_path.with_suffix(".json").read_text(encoding="utf-8"))
    nt = payload["new_traps"][0]
    assert nt["evidence_sha256"] is not None


# ---------------------------------------------------------------------------
# Lint integration: stale evidence is detected.
# ---------------------------------------------------------------------------


def test_lint_passes_when_evidence_unchanged(tmp_path: Path, monkeypatch):
    """Run produces hash; immediately running lint with no source change passes."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
            Classification(id="t2", label="UNRESOLVED", citation=None, note="n"),
        ],
    )
    fake = _fake_provider(output, {"input_tokens": 1, "output_tokens": 1})
    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 0

    # Now lint — no source change → pass.
    lint_result = runner.invoke(app, ["lint", str(doc_path), "--repo", str(repo)])
    assert lint_result.exit_code == 0, lint_result.stdout


def test_lint_flags_stale_evidence_when_cited_line_changes(
    tmp_path: Path, monkeypatch
):
    """The whole point of this PR — cited line edited after run = stale flag."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
            Classification(id="t2", label="UNRESOLVED", citation=None, note="n"),
        ],
    )
    fake = _fake_provider(output, {"input_tokens": 1, "output_tokens": 1})
    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 0

    # Now mutate line 5 of the cited file.
    auth_file = repo / "src" / "auth.py"
    lines = auth_file.read_text(encoding="utf-8").splitlines()
    lines[4] = "completely different line content"
    auth_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Lint must catch the drift.
    lint_result = runner.invoke(app, ["lint", str(doc_path), "--repo", str(repo)])
    assert lint_result.exit_code == 1
    assert "stale evidence" in lint_result.stderr.lower()


def test_lint_ignores_unrelated_lines_when_cited_lines_unchanged(
    tmp_path: Path, monkeypatch
):
    """Hash is per-citation. Mutating an unrelated line must NOT trip stale check."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
            Classification(id="t2", label="UNRESOLVED", citation=None, note="n"),
        ],
    )
    fake = _fake_provider(output, {"input_tokens": 1, "output_tokens": 1})
    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 0

    # Mutate line 18 — unrelated to citation src/auth.py:5.
    auth_file = repo / "src" / "auth.py"
    lines = auth_file.read_text(encoding="utf-8").splitlines()
    lines[17] = "unrelated edit"
    auth_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    lint_result = runner.invoke(app, ["lint", str(doc_path), "--repo", str(repo)])
    assert lint_result.exit_code == 0, lint_result.stdout


def test_lint_skips_stale_check_for_legacy_artifacts_without_hash(
    tmp_path: Path,
):
    """Pre-evidence-hash artifacts (no evidence_sha256) lint clean."""
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    # Hand-write an artifact without evidence_sha256 (simulating older run).
    artifact = {
        "classifications": [
            {
                "id": "t1",
                "label": "REAL",
                "citation": "src/auth.py:5",
                "note": "n",
            },
            {"id": "t2", "label": "UNRESOLVED", "citation": None, "note": "n"},
        ],
        "new_traps": [],
        "spec_mutations": [],
        "decision": "PROCEED_WITH_GUARDS",
    }
    doc_path.with_suffix(".json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    lint_result = runner.invoke(app, ["lint", str(doc_path), "--repo", str(repo)])
    assert lint_result.exit_code == 0, lint_result.stdout
