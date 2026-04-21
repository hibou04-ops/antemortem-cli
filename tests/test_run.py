"""Tests for the `antemortem run` command — mocked API, real filesystem."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from antemortem.cli import app
from antemortem.commands.run import _build_traps_table, _load_files_from_repo
from antemortem.parser import parse_document
from antemortem.schema import AntemortemOutput, Classification, NewTrap

runner = CliRunner()


COMPLETE_DOC = """---
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


def test_build_traps_table_escapes_pipe():
    from antemortem.schema import Trap

    traps = [Trap(id="t1", hypothesis="a | b", type="trap")]
    table = _build_traps_table(traps)
    assert r"a \| b" in table
    assert "| t1 |" in table


def test_load_files_resolves_paths(tmp_path: Path):
    repo = _make_repo(tmp_path)
    doc_text = COMPLETE_DOC
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(doc_text, encoding="utf-8")
    doc = parse_document(doc_path)
    files, warnings = _load_files_from_repo(doc, repo)
    assert len(files) == 1
    assert files[0][0] == "src/auth.py"
    assert "auth line 1" in files[0][1]
    assert warnings == []


def test_load_files_warns_on_missing(tmp_path: Path):
    repo = _make_repo(tmp_path)
    doc_text = COMPLETE_DOC.replace("src/auth.py", "src/ghost.py")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(doc_text, encoding="utf-8")
    doc = parse_document(doc_path)
    files, warnings = _load_files_from_repo(doc, repo)
    assert files == []
    assert any("ghost.py" in w for w in warnings)


def test_run_exits_if_no_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(COMPLETE_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 2


def _fake_provider(output: AntemortemOutput, usage: dict):
    from unittest.mock import MagicMock

    provider = MagicMock()
    provider.name = "anthropic"
    provider.model = "mock-model"
    provider.structured_complete.return_value = (output, usage)
    return provider


def test_run_full_flow_writes_artifact(tmp_path: Path, monkeypatch):
    """End-to-end run with a mocked provider."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(COMPLETE_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    expected = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
            Classification(id="t2", label="GHOST", citation="src/auth.py:10", note="n"),
        ],
        new_traps=[
            NewTrap(
                id="t_new_1",
                hypothesis="logging gap",
                citation="src/auth.py:15",
                note="no audit line",
            ),
        ],
        spec_mutations=["Add audit logging requirement to the spec."],
    )
    fake = _fake_provider(
        expected,
        {
            "input_tokens": 80,
            "output_tokens": 220,
            "cache_creation_input_tokens": 4300,
            "cache_read_input_tokens": 0,
        },
    )

    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])

    assert result.exit_code == 0, result.stdout
    artifact_path = doc_path.with_suffix(".json")
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["classifications"][0]["id"] == "t1"
    assert payload["new_traps"][0]["hypothesis"] == "logging gap"
    assert "audit logging" in payload["spec_mutations"][0]


def test_run_reports_cache_miss(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(COMPLETE_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    expected = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
            Classification(id="t2", label="GHOST", citation="src/auth.py:10", note="n"),
        ]
    )
    fake = _fake_provider(
        expected,
        {
            "input_tokens": 50,
            "output_tokens": 100,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    )

    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])

    assert result.exit_code == 0
    assert "prompt cache did not engage" in result.stdout


def test_run_exits_when_no_traps(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-stub")
    no_traps = """---
name: feat
date: 2026-04-21
---

# x

## 1. The change

x

## 2. Traps hypothesized

No table.

## 3. Recon protocol

- `src/auth.py`
"""
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(no_traps, encoding="utf-8")
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 1


def test_run_exits_when_no_files_resolvable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-stub")
    doc_text = COMPLETE_DOC.replace("src/auth.py", "src/missing.py")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(doc_text, encoding="utf-8")
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 1
