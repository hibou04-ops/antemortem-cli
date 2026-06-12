"""Tests for git-diff scope derivation (git_scope module + `run --diff`)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from antemortem.cli import app
from antemortem.git_scope import GitScopeError, files_from_git_diff

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not available on PATH"
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "src" / "auth.py").write_text("line1\nline2\nline3\n", encoding="utf-8")
    (repo / "src" / "db.py").write_text("dbline1\ndbline2\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_files_from_git_diff_working_changes(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / "src" / "auth.py").write_text("line1\nCHANGED\nline3\n", encoding="utf-8")
    files = files_from_git_diff("working", repo)
    assert files == ["src/auth.py"]


def test_files_from_git_diff_staged(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / "src" / "db.py").write_text("dbline1\nCHANGED\n", encoding="utf-8")
    _git(repo, "add", "src/db.py")
    files = files_from_git_diff("staged", repo)
    assert files == ["src/db.py"]


def test_files_from_git_diff_ref(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / "src" / "auth.py").write_text("line1\nx\nline3\n", encoding="utf-8")
    _git(repo, "commit", "-am", "second")
    files = files_from_git_diff("HEAD~1", repo)
    assert files == ["src/auth.py"]


def test_files_from_git_diff_excludes_deletions(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / "src" / "db.py").unlink()
    # Working-tree deletion: nothing on disk to cite, so it must be dropped.
    files = files_from_git_diff("working", repo)
    assert "src/db.py" not in files


def test_files_from_git_diff_sorted_and_deduped(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / "src" / "auth.py").write_text("a\nb\nc\nd\n", encoding="utf-8")
    (repo / "src" / "db.py").write_text("a\nb\nc\n", encoding="utf-8")
    files = files_from_git_diff("working", repo)
    assert files == ["src/auth.py", "src/db.py"]  # sorted


def test_files_from_git_diff_not_a_repo(tmp_path: Path):
    non_repo = tmp_path / "plain"
    non_repo.mkdir()
    with pytest.raises(GitScopeError, match="not inside a git work tree"):
        files_from_git_diff("working", non_repo)


def test_files_from_git_diff_empty_spec(tmp_path: Path):
    repo = _init_repo(tmp_path)
    with pytest.raises(GitScopeError):
        files_from_git_diff("   ", repo)


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
  - `placeholder.txt`
"""


def test_run_diff_no_changes_fails(tmp_path: Path, monkeypatch):
    """--diff that matches nothing fails with a clear message."""
    repo = _init_repo(tmp_path)
    # placeholder.txt referenced by the doc must exist so the doc itself is sane.
    (repo / "placeholder.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "add placeholder")
    doc = tmp_path / "feat.md"
    doc.write_text(_DOC, encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-stub")
    result = runner.invoke(
        app, ["run", str(doc), "--repo", str(repo), "--diff", "staged"]
    )
    # Staged is empty (clean tree) → no changed files → exit 1.
    assert result.exit_code == 1
    assert "matched no changed files" in result.stderr


def test_run_diff_bad_repo_fails(tmp_path: Path, monkeypatch):
    """--diff against a non-git repo surfaces a usage error."""
    non_repo = tmp_path / "plain"
    (non_repo / "src").mkdir(parents=True)
    (non_repo / "placeholder.txt").write_text("x\n", encoding="utf-8")
    doc = tmp_path / "feat.md"
    doc.write_text(_DOC, encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-stub")
    result = runner.invoke(
        app, ["run", str(doc), "--repo", str(non_repo), "--diff", "working"]
    )
    assert result.exit_code == 2
    assert "--diff scope" in result.stderr


def test_run_diff_merges_changed_files_into_scope(tmp_path: Path, monkeypatch):
    """--diff merges git-changed files into the recon scope and they reach the loader."""
    from unittest.mock import patch

    from antemortem.schema import AntemortemOutput, Classification

    repo = _init_repo(tmp_path)
    (repo / "placeholder.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "add placeholder")
    # Change auth.py in the working tree so --diff working picks it up.
    (repo / "src" / "auth.py").write_text("line1\nCHANGED\nline3\n", encoding="utf-8")

    doc = tmp_path / "feat.md"
    doc.write_text(_DOC, encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-stub")

    captured: dict = {}
    real_loader = None

    def _spy_loader(parsed_doc, repo_root, safety=None):
        captured["files_to_read"] = list(parsed_doc.files_to_read)
        return real_loader(parsed_doc, repo_root, safety)

    from antemortem.commands import run as run_mod

    real_loader = run_mod.load_files_for_recon

    from unittest.mock import MagicMock

    fake = MagicMock()
    fake.name = "anthropic"
    fake.model = "mock-model"
    fake.structured_complete.return_value = (
        AntemortemOutput(
            classifications=[
                Classification(id="t1", label="REAL", citation="src/auth.py:2", note="n"),
            ]
        ),
        {"input_tokens": 1, "output_tokens": 1,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    )

    with patch.object(run_mod, "load_files_for_recon", _spy_loader), \
         patch.object(run_mod, "make_provider", return_value=fake):
        result = runner.invoke(
            app, ["run", str(doc), "--repo", str(repo), "--diff", "working"]
        )

    assert result.exit_code == 0, result.stdout
    # The git-changed file was merged into the recon scope alongside the doc's list.
    assert "src/auth.py" in captured["files_to_read"]
    assert "placeholder.txt" in captured["files_to_read"]
