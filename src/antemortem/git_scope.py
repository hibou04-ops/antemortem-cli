# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Derive the recon file scope from a git diff.

The discipline normally reads the file list from the ``## Recon protocol``
section of the antemortem document — a hand-curated list. ``--diff`` flips
the source of truth: instead of trusting a human to remember every file an
AI agent touched, it asks git which files actually changed and audits
exactly those. This makes the antemortem cover an agent's *real* patch.

Three diff specs are supported, all read-only (``git`` is only ever
invoked with diff/ls-files, never with mutating verbs):

  - ``--diff staged``  → files in the index (``git diff --cached --name-only``)
  - ``--diff HEAD~1``  → files changed vs a ref (``git diff <ref> --name-only``)
  - ``--diff working`` → unstaged + staged tracked changes (``git diff HEAD``)

The returned paths are repo-root-relative, forward-slashed, de-duplicated,
and sorted — the same shape the document loader expects, so the rest of
the run pipeline is unchanged. Deleted files are dropped (there's nothing
on disk to cite).
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitScopeError(RuntimeError):
    """Raised when a git-diff scope cannot be resolved into a file list."""


_STAGED_ALIASES = frozenset({"staged", "cached", "index"})
_WORKING_ALIASES = frozenset({"working", "worktree", "unstaged", "."})


def _run_git(args: list[str], repo_root: Path) -> str:
    """Run a read-only git command in ``repo_root``; return stdout text.

    Raises ``GitScopeError`` with an actionable message when git is
    missing, the directory is not a repo, or the command fails.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:  # git not installed / not on PATH
        raise GitScopeError(
            "git executable not found on PATH. --diff scope requires git. "
            "Install git or pass an explicit Recon protocol file list."
        ) from exc
    if result.returncode != 0:
        stderr = result.stderr.strip() or "git command failed"
        raise GitScopeError(
            f"git {' '.join(args)} failed in {repo_root}: {stderr}"
        )
    return result.stdout


def _is_git_repo(repo_root: Path) -> bool:
    try:
        out = _run_git(["rev-parse", "--is-inside-work-tree"], repo_root)
    except GitScopeError:
        return False
    return out.strip() == "true"


def _diff_args(diff_spec: str) -> list[str]:
    """Translate a user-facing diff spec into git diff arguments.

    Returns the argument list AFTER ``diff``; e.g. ``["--cached"]`` or
    ``["HEAD~1"]``. The ``--name-only`` and diff-filter flags are appended
    by the caller so every spec shares the same output contract.
    """
    spec = diff_spec.strip()
    if not spec:
        raise GitScopeError("--diff scope is empty; pass e.g. 'staged', 'HEAD~1', or 'working'.")
    if spec in _STAGED_ALIASES:
        return ["--cached"]
    if spec in _WORKING_ALIASES:
        # Tracked changes in the working tree (staged + unstaged) vs HEAD.
        return ["HEAD"]
    # Otherwise treat the spec as a ref / ref-range git understands directly,
    # e.g. "HEAD~1", "main", "abc123..def456".
    return [spec]


def files_from_git_diff(diff_spec: str, repo_root: Path) -> list[str]:
    """Return repo-relative paths changed by ``diff_spec``.

    Deleted files are excluded (``--diff-filter=d`` drops deletions) since
    there is no on-disk content to cite. Paths are normalized to forward
    slashes, de-duplicated, and sorted for deterministic output.

    Raises ``GitScopeError`` when ``repo_root`` is not a git work tree or
    the diff command fails.
    """
    repo_root = repo_root.resolve()
    if not _is_git_repo(repo_root):
        raise GitScopeError(
            f"{repo_root} is not inside a git work tree. --diff scope needs a "
            "git repo; pass --repo pointing at the repository root, or use a "
            "hand-listed Recon protocol instead."
        )
    args = ["diff", "--name-only", "--diff-filter=d", *_diff_args(diff_spec)]
    out = _run_git(args, repo_root)
    seen: set[str] = set()
    paths: list[str] = []
    for raw in out.splitlines():
        rel = raw.strip().replace("\\", "/")
        if not rel or rel in seen:
            continue
        seen.add(rel)
        paths.append(rel)
    return sorted(paths)
