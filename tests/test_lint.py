"""Tests for the lint command — schema + citation verification."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from antemortem.cli import app
from antemortem.commands.lint import run_lint

runner = CliRunner()


COMPLETE_DOC = """---
name: feat
date: 2026-04-21
template: basic
---

# Antemortem — feat

## 1. The change

Add validation to the login flow.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | token expiry missed | trap | 60% | from prior incident |
| 2 | race on refresh | worry | 30% | uncertain |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/auth.py`
"""


def _write_repo_with_auth(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 101)) + "\n",
        encoding="utf-8",
    )
    return repo


def test_lint_pass_schema_only(tmp_path: Path):
    doc = tmp_path / "feat.md"
    doc.write_text(COMPLETE_DOC, encoding="utf-8")
    repo = _write_repo_with_auth(tmp_path)
    result = run_lint(doc, repo)
    assert result.ok, result.violations


def test_lint_fails_on_empty_spec(tmp_path: Path):
    doc = tmp_path / "bad.md"
    doc.write_text(
        COMPLETE_DOC.replace("Add validation to the login flow.", ""),
        encoding="utf-8",
    )
    repo = _write_repo_with_auth(tmp_path)
    result = run_lint(doc, repo)
    assert not result.ok
    assert any("spec" in v for v in result.violations)


def test_lint_fails_on_missing_traps(tmp_path: Path):
    no_traps = """---
name: feat
date: 2026-04-21
---

# Antemortem

## 1. The change

x

## 2. Traps hypothesized

No table here.

## 3. Recon protocol

- `src/x.py`
"""
    doc = tmp_path / "bad.md"
    doc.write_text(no_traps, encoding="utf-8")
    repo = _write_repo_with_auth(tmp_path)
    result = run_lint(doc, repo)
    assert not result.ok
    assert any("traps" in v for v in result.violations)


def test_lint_fails_on_missing_files_to_read(tmp_path: Path):
    no_files = """---
name: feat
date: 2026-04-21
---

# Antemortem

## 1. The change

x

## 2. Traps hypothesized

| # | trap | label | P | notes |
|---|------|-------|---|-------|
| 1 | real trap | trap | 50% | n |

## 3. Recon protocol

- Time: 15 min
"""
    doc = tmp_path / "bad.md"
    doc.write_text(no_files, encoding="utf-8")
    repo = _write_repo_with_auth(tmp_path)
    result = run_lint(doc, repo)
    assert not result.ok
    assert any("files_to_read" in v for v in result.violations)


def test_lint_fails_on_bad_frontmatter(tmp_path: Path):
    bad = """---
date: 2026-04-21
---

## 1. The change

x

## 2. Traps

| # | trap | label | P | n |
|---|------|-------|---|---|
| 1 | real | trap | 50% | n |

## 3. Recon protocol

- `src/x.py`
"""
    doc = tmp_path / "bad.md"
    doc.write_text(bad, encoding="utf-8")
    repo = _write_repo_with_auth(tmp_path)
    result = run_lint(doc, repo)
    assert not result.ok
    assert any("document" in v.lower() or "frontmatter" in v.lower() for v in result.violations)


def test_lint_pass_with_valid_artifact(tmp_path: Path):
    doc = tmp_path / "feat.md"
    doc.write_text(COMPLETE_DOC, encoding="utf-8")
    repo = _write_repo_with_auth(tmp_path)

    artifact = doc.with_suffix(".json")
    artifact.write_text(
        json.dumps(
            {
                "classifications": [
                    {"id": "t1", "label": "REAL", "citation": "src/auth.py:10", "note": "n"},
                    {"id": "t2", "label": "GHOST", "citation": "src/auth.py:42", "note": "n"},
                ],
                "new_traps": [],
                "spec_mutations": [],
            }
        ),
        encoding="utf-8",
    )
    result = run_lint(doc, repo)
    assert result.ok, result.violations


def test_lint_fails_when_citation_out_of_range(tmp_path: Path):
    doc = tmp_path / "feat.md"
    doc.write_text(COMPLETE_DOC, encoding="utf-8")
    repo = _write_repo_with_auth(tmp_path)

    artifact = doc.with_suffix(".json")
    artifact.write_text(
        json.dumps(
            {
                "classifications": [
                    {"id": "t1", "label": "REAL", "citation": "src/auth.py:9999", "note": "n"},
                    {"id": "t2", "label": "GHOST", "citation": "src/auth.py:42", "note": "n"},
                ],
                "new_traps": [],
                "spec_mutations": [],
            }
        ),
        encoding="utf-8",
    )
    result = run_lint(doc, repo)
    assert not result.ok
    assert any("out of range" in v for v in result.violations)


def test_lint_fails_when_cited_file_missing(tmp_path: Path):
    doc = tmp_path / "feat.md"
    doc.write_text(COMPLETE_DOC, encoding="utf-8")
    repo = _write_repo_with_auth(tmp_path)

    artifact = doc.with_suffix(".json")
    artifact.write_text(
        json.dumps(
            {
                "classifications": [
                    {"id": "t1", "label": "REAL", "citation": "src/missing.py:1", "note": "n"},
                    {"id": "t2", "label": "GHOST", "citation": "src/auth.py:1", "note": "n"},
                ],
                "new_traps": [],
                "spec_mutations": [],
            }
        ),
        encoding="utf-8",
    )
    result = run_lint(doc, repo)
    assert not result.ok
    assert any("does not exist" in v for v in result.violations)


def test_lint_fails_when_trap_unclassified(tmp_path: Path):
    doc = tmp_path / "feat.md"
    doc.write_text(COMPLETE_DOC, encoding="utf-8")
    repo = _write_repo_with_auth(tmp_path)

    artifact = doc.with_suffix(".json")
    artifact.write_text(
        json.dumps(
            {
                "classifications": [
                    {"id": "t1", "label": "REAL", "citation": "src/auth.py:1", "note": "n"},
                    # t2 missing intentionally
                ],
                "new_traps": [],
                "spec_mutations": [],
            }
        ),
        encoding="utf-8",
    )
    result = run_lint(doc, repo)
    assert not result.ok
    assert any("missing for trap t2" in v for v in result.violations)


def test_lint_allows_unresolved_with_null_citation(tmp_path: Path):
    doc = tmp_path / "feat.md"
    doc.write_text(COMPLETE_DOC, encoding="utf-8")
    repo = _write_repo_with_auth(tmp_path)

    artifact = doc.with_suffix(".json")
    artifact.write_text(
        json.dumps(
            {
                "classifications": [
                    {"id": "t1", "label": "UNRESOLVED", "citation": None, "note": "no evidence"},
                    {"id": "t2", "label": "GHOST", "citation": "src/auth.py:1", "note": "n"},
                ],
                "new_traps": [],
                "spec_mutations": [],
            }
        ),
        encoding="utf-8",
    )
    result = run_lint(doc, repo)
    assert result.ok, result.violations


def test_lint_cli_exit_codes(tmp_path: Path):
    doc = tmp_path / "feat.md"
    doc.write_text(COMPLETE_DOC, encoding="utf-8")
    repo = _write_repo_with_auth(tmp_path)

    ok = runner.invoke(app, ["lint", str(doc), "--repo", str(repo)])
    assert ok.exit_code == 0

    (doc.with_suffix(".json")).write_text(
        json.dumps({"classifications": [], "new_traps": [], "spec_mutations": []}),
        encoding="utf-8",
    )
    fail = runner.invoke(app, ["lint", str(doc), "--repo", str(repo)])
    assert fail.exit_code == 1
