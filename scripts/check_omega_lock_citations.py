#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Tier B docking guard -- verify omega-lock citations against a PINNED checkout.

The antemortem READMEs cite omega-lock by ``src/omega_lock/<file>.py:line``.
Those are CROSS-REPO claims that can silently rot when omega-lock is patched --
exactly the silent-break class the docking hardlock exists to prevent. This
script scans the READMEs for such citations and verifies each against a *pinned*
omega-lock source checkout (pass ``--omega-lock-root`` at an omega-lock @ v0.3.2
checkout; CI uses a pinned ``actions/checkout`` SHA). It reuses antemortem's OWN
``verify_citation`` (file-exists + line-in-range) and adds a per-file semantic
token check for the load-bearing claims, catching a line-number drift that stays
in-range but moved the cited construct.

CI-time checkout != runtime dependency. antemortem keeps zero ``import omega_lock``.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from antemortem.citations import verify_citation

# `src/omega_lock/<path>.py:line` or `...:line-line`. Requires the omega_lock
# namespace + a line number (file-only links like the kill_criteria.py markdown
# link are out of scope -- their correctness is structural, not line-pinned).
_OMEGA_LOCK_CITATION_RE = re.compile(r"src/omega_lock/[^\s:`)\]]+\.py:\d+(?:-\d+)?")

# Per-file semantic token: a citation to this file must point at a line range
# that CONTAINS this token. verify_citation only checks file-exists + line-in-
# range; this catches a drift where omega-lock refactors the file and the cited
# construct moves off the cited line while staying in range.
_EXPECTED_TOKENS = {
    "src/omega_lock/walk_forward.py": "evaluate(",
}

_DEFAULT_READMES = ("README.md", "README_KR.md")


def _cited_lines(omega_lock_root: Path, rel_path: str, start: int, end: int) -> list[str]:
    text = (omega_lock_root / rel_path).read_text(encoding="utf-8", errors="replace").splitlines()
    return text[start - 1 : end]


def check(repo_root: Path, omega_lock_root: Path, readmes: tuple[str, ...]) -> list[str]:
    """Return a list of failure messages (empty == all citations valid)."""
    failures: list[str] = []
    seen: set[str] = set()
    found_any = False
    for readme in readmes:
        path = repo_root / readme
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for citation in _OMEGA_LOCK_CITATION_RE.findall(text):
            if citation in seen:
                continue
            seen.add(citation)
            found_any = True
            result = verify_citation(citation, omega_lock_root)
            if not result.ok:
                failures.append(f"{readme}: {citation} -- {result.reason}")
                continue
            parsed = result.parsed
            assert parsed is not None
            token = _EXPECTED_TOKENS.get(parsed.path)
            if token is not None:
                lines = _cited_lines(omega_lock_root, parsed.path, parsed.start, parsed.end)
                if not any(token in ln for ln in lines):
                    failures.append(
                        f"{readme}: {citation} -- cited line(s) do not contain expected token "
                        f"{token!r} (omega-lock moved the cited construct)"
                    )
    if not found_any:
        print("note: no 'src/omega_lock/<file>.py:line' citations found in the READMEs")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify omega-lock citations in the READMEs against a pinned omega-lock checkout.",
    )
    parser.add_argument(
        "--omega-lock-root",
        required=True,
        type=Path,
        help="Path to a PINNED omega-lock source checkout (e.g. omega-lock @ v0.3.2 / 12559db).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="antemortem-cli repo root (default: parent of scripts/).",
    )
    parser.add_argument(
        "--readme",
        action="append",
        dest="readmes",
        help="README file(s) to scan, relative to --repo-root (default: README.md, README_KR.md).",
    )
    args = parser.parse_args(argv)
    readmes = tuple(args.readmes) if args.readmes else _DEFAULT_READMES

    failures = check(args.repo_root, args.omega_lock_root, readmes)
    if failures:
        print("omega-lock citation drift detected:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("omega-lock citations OK (verified against the pinned checkout).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
