"""Tests for the manual publish-readiness gate."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "publish_readiness.py"
SPEC = importlib.util.spec_from_file_location("publish_readiness", SCRIPT_PATH)
assert SPEC is not None
publish_readiness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = publish_readiness
SPEC.loader.exec_module(publish_readiness)


def _write_repo(root: Path, *, version: str = "1.2.3") -> None:
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

- Publish readiness gate.
""",
        encoding="utf-8",
    )


def _success_runner(commands: list[list[str]]):
    def runner(command, cwd, env, text, encoding, errors, capture_output, check):
        command = list(command)
        commands.append(command)
        if command[:3] == ["git", "-c", f"safe.directory={Path(cwd).as_posix()}"]:
            if "status" in command:
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            if "rev-parse" in command:
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        if command[:3] == [sys.executable, "-m", "build"]:
            dist = Path(cwd) / "dist"
            dist.mkdir(exist_ok=True)
            wheel = dist / "antemortem-1.2.3-py3-none-any.whl"
            sdist = dist / "antemortem-1.2.3.tar.gz"
            wheel.write_text("wheel", encoding="utf-8")
            sdist.write_text("sdist", encoding="utf-8")
            future = time.time() + 5
            os.utime(wheel, (future, future))
            os.utime(sdist, (future, future))
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:4] == [sys.executable, "-m", "twine", "check"]:
            return subprocess.CompletedProcess(command, 0, stdout="PASSED\n", stderr="")
        if command == [sys.executable, "scripts/smoke_wheel_install.py"]:
            return subprocess.CompletedProcess(command, 0, stdout="Wheel smoke test passed.\n", stderr="")
        if command == [sys.executable, "scripts/release_audit.py"]:
            return subprocess.CompletedProcess(command, 0, stdout="Release audit passed.\n", stderr="")
        if command == [sys.executable, "scripts/check_repo_consistency.py"]:
            return subprocess.CompletedProcess(command, 0, stdout="Repository consistency check passed.\n", stderr="")
        if command == [sys.executable, "scripts/generate_readme_claims.py", "--check"]:
            return subprocess.CompletedProcess(command, 0, stdout="Generated README claim blocks are current.\n", stderr="")
        if command == ["antemortem", "eval", "benchmarks/golden_cases", "--json"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"metrics": {"decision_accuracy": 1.0}, "totals": {"cases": 1}}),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    return runner


def _assert_publish_ready(exit_code: int, summary: dict[str, object]) -> None:
    if exit_code != 0:
        failed = [check for check in summary["checks"] if check["classification"] != "PASS"]
        raise AssertionError(json.dumps(failed, indent=2, sort_keys=True))


def test_publish_readiness_all_checks_pass_with_mocked_subprocesses(tmp_path: Path):
    _write_repo(tmp_path)
    commands: list[list[str]] = []

    exit_code, summary = publish_readiness.run_publish_readiness(
        tmp_path,
        runner=_success_runner(commands),
    )

    _assert_publish_ready(exit_code, summary)
    assert summary["ok"] is True
    assert summary["failed_count"] == 0
    assert {check["classification"] for check in summary["checks"]} == {"PASS"}
    assert any(command[:3] == [sys.executable, "-m", "build"] for command in commands)
    assert any(command[:4] == [sys.executable, "-m", "twine", "check"] for command in commands)


def test_missing_build_module_reports_tooling_missing(tmp_path: Path):
    _write_repo(tmp_path)
    commands: list[list[str]] = []

    def runner(command, *args, **kwargs):
        command = list(command)
        if command[:3] == [sys.executable, "-m", "build"]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="No module named build")
        return _success_runner(commands)(command, *args, **kwargs)

    exit_code, summary = publish_readiness.run_publish_readiness(tmp_path, runner=runner)

    build = summary["checks"][-1]
    assert exit_code == 1
    assert build["label"] == "package build"
    assert build["classification"] == "TOOLING_MISSING"


def test_missing_twine_module_reports_tooling_missing(tmp_path: Path):
    _write_repo(tmp_path)
    commands: list[list[str]] = []

    def runner(command, *args, **kwargs):
        command = list(command)
        if command[:4] == [sys.executable, "-m", "twine", "check"]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="No module named twine")
        return _success_runner(commands)(command, *args, **kwargs)

    exit_code, summary = publish_readiness.run_publish_readiness(tmp_path, runner=runner)

    failed = summary["checks"][-1]
    assert exit_code == 1
    assert failed["label"] == "twine check"
    assert failed["classification"] == "TOOLING_MISSING"


def test_package_build_failure_reports_fail(tmp_path: Path):
    _write_repo(tmp_path)
    commands: list[list[str]] = []

    def runner(command, *args, **kwargs):
        command = list(command)
        if command[:3] == [sys.executable, "-m", "build"]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 2, stdout="", stderr="backend failed")
        return _success_runner(commands)(command, *args, **kwargs)

    exit_code, summary = publish_readiness.run_publish_readiness(tmp_path, runner=runner)

    assert exit_code == 1
    assert summary["checks"][-1]["label"] == "package build"
    assert summary["checks"][-1]["classification"] == "FAIL"


def test_wheel_smoke_failure_reports_fail(tmp_path: Path):
    _write_repo(tmp_path)
    commands: list[list[str]] = []

    def runner(command, *args, **kwargs):
        command = list(command)
        if command == [sys.executable, "scripts/smoke_wheel_install.py"]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 8, stdout="", stderr="doctor command failed")
        return _success_runner(commands)(command, *args, **kwargs)

    exit_code, summary = publish_readiness.run_publish_readiness(tmp_path, runner=runner)

    assert exit_code == 1
    assert summary["checks"][-1]["label"] == "wheel smoke install"
    assert summary["checks"][-1]["classification"] == "FAIL"


def test_dirty_git_tree_blocks_unless_allow_dirty(tmp_path: Path):
    _write_repo(tmp_path)
    commands: list[list[str]] = []

    def runner(command, *args, **kwargs):
        command = list(command)
        if command[:3] == ["git", "-c", f"safe.directory={tmp_path.as_posix()}"] and "status" in command:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=" M README.md\n", stderr="")
        return _success_runner(commands)(command, *args, **kwargs)

    blocked_code, blocked = publish_readiness.run_publish_readiness(tmp_path, runner=runner)
    allowed_code, allowed = publish_readiness.run_publish_readiness(
        tmp_path,
        allow_dirty=True,
        runner=_success_runner([]),
    )

    assert blocked_code == 1
    assert blocked["checks"][0]["classification"] == "GIT_STATE_BLOCKED"
    _assert_publish_ready(allowed_code, allowed)
    assert allowed["checks"][0]["classification"] == "PASS"


def test_json_output_is_stable(tmp_path: Path):
    _write_repo(tmp_path)
    exit_code, summary = publish_readiness.run_publish_readiness(
        tmp_path,
        runner=_success_runner([]),
    )
    payload = json.loads(json.dumps(summary, sort_keys=True))

    _assert_publish_ready(exit_code, summary)
    assert payload["ok"] is True
    assert payload["version"] == "1.2.3"
    assert payload["checks"][0] == {
        "classification": "PASS",
        "command": "git status --porcelain",
        "exit_code": 0,
        "label": "working tree",
        "message": "working tree is clean",
        "next": "none",
    }


def test_continue_on_error_reports_multiple_blockers(tmp_path: Path):
    _write_repo(tmp_path)
    commands: list[list[str]] = []

    def runner(command, *args, **kwargs):
        command = list(command)
        if command[:3] == ["git", "-c", f"safe.directory={tmp_path.as_posix()}"] and "status" in command:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=" M README.md\n", stderr="")
        if command[:3] == [sys.executable, "-m", "build"]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="No module named build")
        if command[:4] == [sys.executable, "-m", "twine", "check"]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="No module named twine")
        return _success_runner(commands)(command, *args, **kwargs)

    exit_code, summary = publish_readiness.run_publish_readiness(
        tmp_path,
        continue_on_error=True,
        runner=runner,
    )

    classifications = [check["classification"] for check in summary["checks"]]
    assert exit_code == 1
    assert "GIT_STATE_BLOCKED" in classifications
    assert classifications.count("TOOLING_MISSING") >= 2
    assert summary["failed_count"] >= 3
