"""Tests for the Tier B omega-lock citation-drift guard (B3)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_omega_lock_citations.py"
_SPEC = importlib.util.spec_from_file_location("check_omega_lock_citations", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
checker = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = checker
_SPEC.loader.exec_module(checker)


def _make_omega_lock(root: Path, *, evaluate_line: int = 153, total: int = 160) -> None:
    """Create a fake omega-lock checkout with walk_forward.py whose
    ``evaluate_line`` holds the test_target.evaluate() call."""
    target = root / "src" / "omega_lock" / "walk_forward.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# line {i}" for i in range(1, total + 1)]
    lines[evaluate_line - 1] = "            r = self.test_target.evaluate(gp.params)"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _readme(repo: Path, body: str) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "README.md").write_text(body, encoding="utf-8")


def test_valid_citation_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _readme(repo, "Citation: src/omega_lock/walk_forward.py:153 (omega-lock v0.3.0)\n")
    ol = tmp_path / "omega_lock_pin"
    ol.mkdir()
    _make_omega_lock(ol, evaluate_line=153)
    assert checker.check(repo, ol, ("README.md",)) == []


def test_out_of_range_citation_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _readme(repo, "src/omega_lock/walk_forward.py:999\n")
    ol = tmp_path / "omega_lock_pin"
    ol.mkdir()
    _make_omega_lock(ol, total=160)
    failures = checker.check(repo, ol, ("README.md",))
    assert len(failures) == 1 and "999" in failures[0]


def test_semantic_token_drift_fails(tmp_path: Path) -> None:
    # Cited line is in range but no longer holds the evaluate() call -> drift.
    repo = tmp_path / "repo"
    _readme(repo, "src/omega_lock/walk_forward.py:10\n")
    ol = tmp_path / "omega_lock_pin"
    ol.mkdir()
    _make_omega_lock(ol, evaluate_line=153, total=160)
    failures = checker.check(repo, ol, ("README.md",))
    assert len(failures) == 1 and "evaluate(" in failures[0]


def test_file_only_link_is_out_of_scope(tmp_path: Path) -> None:
    # A file-only omega_lock link (no :line) is not a line-pinned citation.
    repo = tmp_path / "repo"
    _readme(
        repo,
        "[`src/omega_lock/kill_criteria.py`]"
        "(https://github.com/hibou04-ops/omega-lock/blob/v0.3.0/src/omega_lock/kill_criteria.py)\n",
    )
    ol = tmp_path / "omega_lock_pin"
    ol.mkdir()
    _make_omega_lock(ol)
    # No line-pinned citation -> nothing to verify, no failure.
    assert checker.check(repo, ol, ("README.md",)) == []
