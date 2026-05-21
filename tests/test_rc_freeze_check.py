"""Tests for the release-candidate freeze checker."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "rc_freeze_check.py"
SPEC = importlib.util.spec_from_file_location("rc_freeze_check", SCRIPT_PATH)
assert SPEC is not None
rc_freeze_check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = rc_freeze_check
SPEC.loader.exec_module(rc_freeze_check)


def _write_minimal_repo(root: Path, *, version: str = "1.2.3") -> None:
    (root / "pyproject.toml").write_text(
        f"""\
[project]
name = "antemortem"
version = "{version}"
""",
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        f"""\
# Changelog

## [{version}] - 2026-05-22

### Added

- Release-candidate checklist.
""",
        encoding="utf-8",
    )
    for name in rc_freeze_check.README_FILES:
        (root / name).write_text(
            "Generated claims: docs/generated/claims.md and docs/generated/claims_kr.md\n",
            encoding="utf-8",
        )
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scripts" / "release_audit.py").write_text("# release audit\n", encoding="utf-8")
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")


def _release_audit_payload(*, pytest_status: str = "passed") -> str:
    return json.dumps(
        {
            "ok": True,
            "failed_count": 0,
            "steps": [
                {"command": "pytest -q", "status": pytest_status, "exit_code": 0},
                {
                    "command": "python scripts/check_repo_consistency.py",
                    "status": "passed",
                    "exit_code": 0,
                },
                {
                    "command": "python scripts/generate_readme_claims.py --check",
                    "status": "passed",
                    "exit_code": 0,
                },
                {
                    "command": "antemortem eval benchmarks/golden_cases --json",
                    "status": "passed",
                    "exit_code": 0,
                },
            ],
        }
    )


def _success_runner(commands: list[list[str]]):
    def runner(command, cwd, env, text, capture_output, check, **kwargs):
        command = list(command)
        commands.append(command)
        if command[:2] == [sys.executable, "scripts/release_audit.py"]:
            return subprocess.CompletedProcess(command, 0, stdout=_release_audit_payload(), stderr="")
        if command[:2] == ["git", "-c"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout='{"metrics": {"decision_accuracy": 1.0}}', stderr="")

    return runner


def test_rc_freeze_success_uses_release_audit_coverage(tmp_path: Path):
    _write_minimal_repo(tmp_path)
    commands: list[list[str]] = []

    exit_code, summary = rc_freeze_check.run_freeze_check(
        tmp_path,
        runner=_success_runner(commands),
    )

    assert exit_code == 0
    assert summary["ok"] is True
    assert [check["label"] for check in summary["checks"]].count("pytest") == 1
    pytest_check = next(check for check in summary["checks"] if check["label"] == "pytest")
    assert pytest_check["message"] == "covered by release_audit.py output"
    assert [sys.executable, "scripts/release_audit.py", "--continue-on-error", "--json"] in commands


def test_rc_freeze_continue_on_error_records_static_failures(tmp_path: Path):
    _write_minimal_repo(tmp_path, version="0.0.0.dev0")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("TODO: remove before release\n", encoding="utf-8")
    commands: list[list[str]] = []

    exit_code, summary = rc_freeze_check.run_freeze_check(
        tmp_path,
        continue_on_error=True,
        allow_dirty=True,
        runner=_success_runner(commands),
    )

    failed = {check["label"] for check in summary["checks"] if check["status"] == "failed"}
    assert exit_code == 1
    assert {"pyproject version", "CHANGELOG entry", "README generated claims", "public TODO/FIXME"} <= failed
    assert summary["failed_count"] >= 4


def test_rc_freeze_dist_freshness_failure_is_actionable(tmp_path: Path):
    _write_minimal_repo(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    artifact = dist / "antemortem-1.2.3-py3-none-any.whl"
    artifact.write_text("old wheel", encoding="utf-8")
    old = time.time() - 1000
    os.utime(artifact, (old, old))
    new = time.time()
    os.utime(tmp_path / "src" / "module.py", (new, new))

    exit_code, summary = rc_freeze_check.run_freeze_check(
        tmp_path,
        continue_on_error=True,
        allow_dirty=True,
        runner=_success_runner([]),
    )

    dist_check = next(check for check in summary["checks"] if check["label"] == "dist artifacts")
    assert exit_code == 1
    assert dist_check["status"] == "failed"
    assert "python -m build" in dist_check["next"]


def test_rc_freeze_parent_release_audit_mode_skips_child_audit(tmp_path: Path):
    _write_minimal_repo(tmp_path)
    commands: list[list[str]] = []

    exit_code, summary = rc_freeze_check.run_freeze_check(
        tmp_path,
        allow_dirty=True,
        runner=_success_runner(commands),
        env={"ANTEMORTEM_RELEASE_AUDIT_PARENT": "1"},
    )

    assert exit_code == 0
    release_audit = summary["checks"][0]
    assert release_audit["message"] == "running under release_audit.py parent command"
    assert not any(command[:2] == [sys.executable, "scripts/release_audit.py"] for command in commands)
