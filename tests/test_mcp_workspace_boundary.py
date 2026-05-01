# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Reviewer P1: MCP workspace boundary opt-in via ANTEMORTEM_WORKSPACE_ROOT.

Pre-fix the MCP scaffold tool accepted any ``output_dir`` and built
files there; the run tool accepted any ``document`` / ``repo``. On
HTTP-transport MCP exposed beyond localhost this would let a remote
caller scribble or read anywhere on the server filesystem.

Post-fix:

- When ``ANTEMORTEM_WORKSPACE_ROOT`` is unset (default — local stdio
  use), no boundary is applied. Backward-compat with all prior tests
  that pass tmp_path values outside the repo.
- When set, every path argument must resolve under the root. ``..``
  traversal, absolute paths outside, and symlinks-out all raise
  ``ValueError``.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

mcp = pytest.importorskip("mcp")


def _scaffold(**kwargs):
    from antemortem.mcp.server import scaffold
    return scaffold(**kwargs)


def _run(**kwargs):
    from antemortem.mcp.server import run
    return run(**kwargs)


# ---------------------------------------------------------------------------
# Default (env unset): no boundary applied.
# ---------------------------------------------------------------------------


def test_scaffold_works_without_workspace_root_set(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTEMORTEM_WORKSPACE_ROOT", raising=False)
    out_dir = tmp_path / "antemortem"
    result = _scaffold(name="feat", output_dir=str(out_dir))
    assert (out_dir / "feat.md").exists()
    assert "feat.md" in result["path"]


# ---------------------------------------------------------------------------
# When env set: boundary enforced.
# ---------------------------------------------------------------------------


def test_scaffold_inside_workspace_root_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTEMORTEM_WORKSPACE_ROOT", str(tmp_path))
    out_dir = tmp_path / "antemortem"
    result = _scaffold(name="feat", output_dir=str(out_dir))
    assert (out_dir / "feat.md").exists()


def test_scaffold_with_dotdot_escape_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTEMORTEM_WORKSPACE_ROOT", str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()
    with pytest.raises(ValueError, match="escapes the MCP workspace"):
        _scaffold(name="feat", output_dir="../escape")


def test_scaffold_with_absolute_path_outside_root_rejected(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("ANTEMORTEM_WORKSPACE_ROOT", str(ws))
    with pytest.raises(ValueError, match="escapes the MCP workspace"):
        _scaffold(name="feat", output_dir=str(other))


def test_scaffold_relative_path_resolved_under_workspace(tmp_path, monkeypatch):
    """Relative paths land under the workspace root, not the process CWD."""
    monkeypatch.setenv("ANTEMORTEM_WORKSPACE_ROOT", str(tmp_path))
    result = _scaffold(name="feat", output_dir="antemortem")
    assert (tmp_path / "antemortem" / "feat.md").exists()


# ---------------------------------------------------------------------------
# run-side: document and repo args go through the same resolver.
# ---------------------------------------------------------------------------


def test_run_rejects_document_outside_workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    other_doc = tmp_path / "elsewhere.md"
    other_doc.write_text("---\nname: x\n---\n", encoding="utf-8")
    monkeypatch.setenv("ANTEMORTEM_WORKSPACE_ROOT", str(ws))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    with pytest.raises(ValueError, match="document.*escapes the MCP workspace"):
        _run(document=str(other_doc))


def test_run_rejects_repo_outside_workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "feat.md").write_text(
        "---\nname: feat\ndate: 2026-04-21\ntemplate: basic\n---\n\n"
        "# x\n\n## 1. The change\n\nx.\n\n"
        "## 2. Traps hypothesized\n\n"
        "| # | trap | label | P(issue) | notes |\n"
        "|---|------|-------|----------|-------|\n"
        "| 1 | x | trap | 60% | n |\n\n"
        "## 3. Recon protocol\n\n"
        "- **Files handed to the model:**\n"
        "  - `src/auth.py`\n",
        encoding="utf-8",
    )
    other_repo = tmp_path / "elsewhere"
    other_repo.mkdir()
    monkeypatch.setenv("ANTEMORTEM_WORKSPACE_ROOT", str(ws))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    with pytest.raises(ValueError, match="repo.*escapes the MCP workspace"):
        _run(document=str(ws / "feat.md"), repo=str(other_repo))
