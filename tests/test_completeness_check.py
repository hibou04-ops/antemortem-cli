# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Tests for `_check_classification_coverage` — completeness hard fail.

Without this gate, a provider that returned an empty or partial
classification list would still produce a SAFE_TO_PROCEED artifact
(decision.compute_decision returns SAFE when no REAL findings exist,
including the case of zero classifications). The lint command would
catch the mismatch later, but only if the user runs lint — the run-time
artifact is the artifact CI consumes.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from antemortem.cli import app
from antemortem.commands.run import _check_classification_coverage
from antemortem.providers import ProviderError
from antemortem.schema import AntemortemOutput, Classification

runner = CliRunner()


# ---------------------------------------------------------------------------
# Unit-level: the helper itself.
# ---------------------------------------------------------------------------


def _cls(id_: str) -> Classification:
    return Classification(id=id_, label="REAL", citation="src/x.py:1", note="n")


def test_coverage_passes_when_ids_match():
    expected = {"t1", "t2"}
    classifications = [_cls("t1"), _cls("t2")]
    _check_classification_coverage(expected, classifications)  # no raise


def test_coverage_fails_on_missing():
    expected = {"t1", "t2"}
    with pytest.raises(ProviderError, match="missing classifications"):
        _check_classification_coverage(expected, [_cls("t1")])


def test_coverage_fails_on_extra():
    expected = {"t1"}
    with pytest.raises(ProviderError, match="unknown trap id"):
        _check_classification_coverage(expected, [_cls("t1"), _cls("t99")])


def test_coverage_fails_on_empty_classifications():
    """The most dangerous case — provider returned zero — must hard fail."""
    expected = {"t1", "t2"}
    with pytest.raises(ProviderError, match="missing classifications"):
        _check_classification_coverage(expected, [])


def test_coverage_reports_both_missing_and_extra():
    expected = {"t1", "t2"}
    with pytest.raises(ProviderError) as exc_info:
        _check_classification_coverage(expected, [_cls("t1"), _cls("t99")])
    msg = str(exc_info.value)
    assert "missing classifications" in msg
    assert "unknown trap id" in msg


# ---------------------------------------------------------------------------
# Integration: full `run` CLI path with mocked provider.
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
| 2 | race on refresh | worry | 30% | uncertain |

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
    from unittest.mock import MagicMock

    provider = MagicMock()
    provider.name = "anthropic"
    provider.model = "mock-model"
    provider.structured_complete.return_value = (output, usage)
    return provider


def test_run_aborts_when_provider_returns_empty(tmp_path: Path, monkeypatch):
    """No classifications returned → no artifact, exit code 1."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    bad_output = AntemortemOutput(classifications=[], new_traps=[])
    fake = _fake_provider(bad_output, {"input_tokens": 1, "output_tokens": 1})

    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])

    assert result.exit_code == 1
    assert not doc_path.with_suffix(".json").exists(), (
        "Artifact must NOT be written when coverage check fails"
    )
    assert "coverage mismatch" in result.stderr


def test_run_aborts_when_provider_returns_partial(tmp_path: Path, monkeypatch):
    """Provider classified t1 only; t2 missing → fail, no artifact."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    partial_output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
        ],
    )
    fake = _fake_provider(partial_output, {"input_tokens": 1, "output_tokens": 1})

    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])

    assert result.exit_code == 1
    assert "t2" in result.stderr  # the missing trap should be named


def test_run_aborts_when_provider_returns_unknown_id(tmp_path: Path, monkeypatch):
    """Provider classified an id not in the input table → fail."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    bogus_output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
            Classification(id="t2", label="GHOST", citation="src/auth.py:10", note="n"),
            Classification(id="t999", label="REAL", citation="src/auth.py:7", note="n"),
        ],
    )
    fake = _fake_provider(bogus_output, {"input_tokens": 1, "output_tokens": 1})

    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])

    assert result.exit_code == 1
    assert "t999" in result.stderr


def test_run_proceeds_when_coverage_complete(tmp_path: Path, monkeypatch):
    """Sanity: matching IDs do not trip the gate."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    good_output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
            Classification(id="t2", label="GHOST", citation="src/auth.py:10", note="n"),
        ],
    )
    fake = _fake_provider(good_output, {"input_tokens": 1, "output_tokens": 1})

    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])

    assert result.exit_code == 0, result.stdout
    assert doc_path.with_suffix(".json").exists()


# ---------------------------------------------------------------------------
# MCP path: same gate must apply to mcp.run().
# ---------------------------------------------------------------------------


def test_mcp_run_raises_on_partial_coverage(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    from antemortem.mcp.server import run as mcp_run

    partial_output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
        ],
    )
    fake = _fake_provider(partial_output, {"input_tokens": 1, "output_tokens": 1})
    with patch("antemortem.mcp.server.make_provider", return_value=fake):
        with pytest.raises(RuntimeError, match="coverage mismatch"):
            mcp_run(document=str(doc_path), repo=str(repo))
