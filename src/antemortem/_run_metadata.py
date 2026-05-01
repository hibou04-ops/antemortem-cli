# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Helpers for capturing per-run provenance metadata.

Reviewer P1: a publishable audit artifact needs more than the LLM's
output. Which version of the tool produced it? Which provider/model?
Which git commit was the repo at? What files actually got loaded?
This module assembles that metadata into a ``RunMetadata`` record.
"""
from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from antemortem import __version__ as ANTEMORTEM_VERSION
from antemortem.schema import LoadedFile, RunMetadata


def _git_state(repo_root: Path) -> tuple[str | None, bool | None]:
    """Best-effort capture of (commit_hash, dirty_flag) for ``repo_root``.

    Returns ``(None, None)`` when git isn't available or the repo isn't
    a git checkout — reproducibility is informational, not a hard
    requirement, so missing git data doesn't fail the run.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if commit.returncode != 0:
            return None, None
        commit_hash = commit.stdout.strip() or None
        # `git status --porcelain` outputs nothing on a clean tree.
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        dirty = bool(status.stdout.strip())
        return commit_hash, dirty
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None, None


def _file_metas(files: list[tuple[str, str]]) -> list[LoadedFile]:
    """Compute LoadedFile entries for the files that actually loaded.

    SHA-256 covers the content as-fed-to-LLM (post-redaction if
    --redact-secrets was passed) so the artifact reflects what the
    model saw, not what was on disk before redaction.
    """
    out: list[LoadedFile] = []
    for path, content in files:
        encoded = content.encode("utf-8")
        out.append(
            LoadedFile(
                path=path.replace("\\", "/"),
                sha256=hashlib.sha256(encoded).hexdigest(),
                byte_len=len(encoded),
            )
        )
    return out


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_run_metadata(
    *,
    provider: str,
    model: str,
    repo_root: Path,
    system_prompt: str,
    user_payload: str,
    files: list[tuple[str, str]],
    warnings: list[str],
) -> RunMetadata:
    """Assemble RunMetadata for the artifact.

    All inputs are already in hand by the time the run wraps up; this
    function is pure aside from the optional git state probe.
    """
    git_commit, git_dirty = _git_state(repo_root)
    return RunMetadata(
        antemortem_version=ANTEMORTEM_VERSION,
        provider=provider,
        model=model,
        repo_root=str(repo_root),
        repo_git_commit=git_commit,
        repo_git_dirty=git_dirty,
        prompt_sha256=_sha256(system_prompt),
        payload_sha256=_sha256(user_payload),
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        files_loaded=_file_metas(files),
        warnings=list(warnings),
    )
