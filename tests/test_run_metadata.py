# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Reviewer P1: artifact provenance via RunMetadata.

Pre-fix the artifact carried only the LLM's output. Reviewers reading
it later couldn't tell:
  - which version of antemortem produced it
  - which provider/model
  - which repo commit
  - which files actually fed the model (vs were listed but skipped)
  - what the prompt + payload looked like

Post-fix every run attaches a ``RunMetadata`` block.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from antemortem._run_metadata import build_run_metadata
from antemortem.cli import app
from antemortem.schema import (
    AntemortemOutput,
    Classification,
    LoadedFile,
    RunMetadata,
)


# ---------------------------------------------------------------------------
# build_run_metadata: pure helper.
# ---------------------------------------------------------------------------


def test_build_run_metadata_captures_versions_and_hashes(tmp_path):
    files = [("src/auth.py", "x = 1\n")]
    meta = build_run_metadata(
        provider="anthropic",
        model="claude-opus-4-7",
        repo_root=tmp_path,
        system_prompt="prompt",
        user_payload="payload",
        files=files,
        warnings=["a warning"],
    )
    assert isinstance(meta, RunMetadata)
    assert meta.provider == "anthropic"
    assert meta.model == "claude-opus-4-7"
    assert meta.prompt_sha256 == hashlib.sha256(b"prompt").hexdigest()
    assert meta.payload_sha256 == hashlib.sha256(b"payload").hexdigest()
    assert meta.warnings == ["a warning"]
    assert len(meta.files_loaded) == 1
    lf = meta.files_loaded[0]
    assert lf.path == "src/auth.py"
    assert lf.byte_len == len(b"x = 1\n")
    assert lf.sha256 == hashlib.sha256(b"x = 1\n").hexdigest()


def test_build_run_metadata_normalizes_windows_paths(tmp_path):
    meta = build_run_metadata(
        provider="anthropic", model="m", repo_root=tmp_path,
        system_prompt="x", user_payload="x",
        files=[("src\\auth.py", "x\n")],
        warnings=[],
    )
    assert meta.files_loaded[0].path == "src/auth.py"


def test_build_run_metadata_records_iso_timestamp(tmp_path):
    meta = build_run_metadata(
        provider="anthropic", model="m", repo_root=tmp_path,
        system_prompt="x", user_payload="x", files=[], warnings=[],
    )
    # Parse the timestamp — round-trip-safe ISO-8601 is required for
    # downstream tooling.
    from datetime import datetime
    dt = datetime.fromisoformat(meta.created_at.replace("Z", "+00:00"))
    assert dt.tzinfo is not None  # must include timezone info


def test_build_run_metadata_git_state_optional(tmp_path):
    """Empty directory (not a git repo) — git state is None, not an error."""
    meta = build_run_metadata(
        provider="anthropic", model="m", repo_root=tmp_path,
        system_prompt="x", user_payload="x", files=[], warnings=[],
    )
    # Don't assume git is/isn't installed in CI; just assert it's
    # one of (None, str) and (None, bool):
    assert meta.repo_git_commit is None or isinstance(meta.repo_git_commit, str)
    assert meta.repo_git_dirty is None or isinstance(meta.repo_git_dirty, bool)


# ---------------------------------------------------------------------------
# Schema-level: RunMetadata is optional on AntemortemOutput.
# ---------------------------------------------------------------------------


def test_antemortem_output_run_metadata_defaults_to_none():
    output = AntemortemOutput()
    assert output.run_metadata is None


def test_antemortem_output_round_trips_run_metadata():
    meta = RunMetadata(
        antemortem_version="0.7.0",
        provider="openai",
        model="gpt-4o",
        repo_root="/tmp/repo",
        prompt_sha256="a" * 64,
        payload_sha256="b" * 64,
        created_at="2026-05-02T12:00:00+00:00",
        files_loaded=[LoadedFile(path="x.py", sha256="c" * 64, byte_len=10)],
        warnings=[],
    )
    output = AntemortemOutput(run_metadata=meta)
    s = output.model_dump_json()
    rt = AntemortemOutput.model_validate_json(s)
    assert rt.run_metadata == meta


# ---------------------------------------------------------------------------
# CLI run writes run_metadata to the artifact.
# ---------------------------------------------------------------------------


_DOC = """---
name: feat
date: 2026-04-21
template: basic
---

# Antemortem — feat

## 1. The change

Refactor.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | x | trap | 60% | n |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/auth.py`
"""


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text(
        "\n".join(f"l{i}" for i in range(20)) + "\n",
        encoding="utf-8",
    )
    return repo


def _provider_returning(output):
    p = MagicMock()
    p.name = "anthropic"
    p.model = "mock-model"
    p.structured_complete.return_value = (output, {
        "input_tokens": 10, "output_tokens": 20,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
    })
    return p


runner = CliRunner()


def test_cli_run_artifact_carries_run_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    repo = _make_repo(tmp_path)
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="GHOST", citation="src/auth.py:5", note="x"),
        ],
    )
    with patch("antemortem.commands.run.make_provider", return_value=_provider_returning(output)):
        runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])

    artifact = json.loads((tmp_path / "feat.json").read_text(encoding="utf-8"))
    assert artifact.get("run_metadata") is not None
    rm = artifact["run_metadata"]
    assert rm["provider"] == "anthropic"
    assert rm["model"] == "mock-model"
    assert len(rm["files_loaded"]) == 1
    assert rm["files_loaded"][0]["path"] == "src/auth.py"


def test_mcp_run_response_carries_run_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    repo = _make_repo(tmp_path)
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")

    from antemortem.mcp.server import run as mcp_run

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="GHOST", citation="src/auth.py:5", note="x"),
        ],
    )
    with patch("antemortem.mcp.server.make_provider", return_value=_provider_returning(output)):
        result = mcp_run(document=str(doc_path), repo=str(repo))

    assert result.get("run_metadata") is not None
    assert result["run_metadata"]["provider"] == "anthropic"
