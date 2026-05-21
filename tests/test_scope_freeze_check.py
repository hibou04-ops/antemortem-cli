"""Tests for the release scope-freeze checker."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "scope_freeze_check.py"
SPEC = importlib.util.spec_from_file_location("scope_freeze_check", SCRIPT_PATH)
assert SPEC is not None
scope_freeze_check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = scope_freeze_check
SPEC.loader.exec_module(scope_freeze_check)


COMMANDS = ("init", "doctor", "run", "lint", "evidence", "gate", "eval")


def _write_doc(root: Path, text: str, name: str = "README.md") -> tuple[str, Path]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return name, path


def test_current_public_docs_pass_scope_freeze_check():
    issues = scope_freeze_check.check_scope_freeze(ROOT)
    scope_doc = (ROOT / "docs" / "scope_freeze.md").read_text(encoding="utf-8")
    release_doc = (ROOT / "docs" / "release_hygiene.md").read_text(encoding="utf-8")

    assert issues == []
    assert "verification and release-hygiene release" in scope_doc
    assert "python scripts/scope_freeze_check.py" in scope_doc
    assert "[Scope Freeze](scope_freeze.md)" in release_doc


def test_detects_near_term_feature_promise(tmp_path: Path):
    rel, _ = _write_doc(tmp_path, "# Docs\n\nComing soon: hosted dashboard support.\n")

    issues = scope_freeze_check.check_scope_freeze(
        tmp_path,
        public_docs=[rel],
        commands=COMMANDS,
    )

    assert [issue.code for issue in issues] == ["feature-promise"]
    assert "hosted dashboard" in issues[0].snippet


def test_detects_unimplemented_command_as_current_feature(tmp_path: Path):
    rel, _ = _write_doc(tmp_path, "# Docs\n\nUse `antemortem plan` before every diff.\n")

    issues = scope_freeze_check.check_scope_freeze(
        tmp_path,
        public_docs=[rel],
        commands=COMMANDS,
    )

    assert [issue.code for issue in issues] == ["unimplemented-command"]
    assert "`plan`" in issues[0].message


def test_allows_deferred_roadmap_command_reference(tmp_path: Path):
    rel, _ = _write_doc(
        tmp_path,
        "# Docs\n\n## Deferred roadmap\n\n- Add a run-diff command only after tests exist.\n",
    )

    issues = scope_freeze_check.check_scope_freeze(
        tmp_path,
        public_docs=[rel],
        commands=COMMANDS,
    )

    assert issues == []


def test_detects_superiority_claim(tmp_path: Path):
    rel, _ = _write_doc(tmp_path, "# Docs\n\nThe best AI code review workflow for teams.\n")

    issues = scope_freeze_check.check_scope_freeze(
        tmp_path,
        public_docs=[rel],
        commands=COMMANDS,
    )

    assert [issue.code for issue in issues] == ["superiority-claim"]


def test_allowlist_can_document_intentional_exception(tmp_path: Path):
    rel, _ = _write_doc(tmp_path, "# Docs\n\nComing soon: migration helper.\n")
    allowlist = tmp_path / "allow.toml"
    allowlist.write_text(
        """
[[allow]]
code = "feature-promise"
path = "README.md"
contains = "migration helper"
reason = "temporary fixture"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    issues = scope_freeze_check.check_scope_freeze(
        tmp_path,
        public_docs=[rel],
        commands=COMMANDS,
        allowlist_path=allowlist,
    )

    assert issues == []
