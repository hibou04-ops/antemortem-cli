"""Tests for the local release audit orchestrator."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "release_audit.py"
SPEC = importlib.util.spec_from_file_location("release_audit", SCRIPT_PATH)
assert SPEC is not None
release_audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = release_audit
SPEC.loader.exec_module(release_audit)


def _success_runner(commands: list[list[str]]):
    def runner(command, cwd, env, text, capture_output, check, **kwargs):
        commands.append(list(command))
        if list(command)[:3] == [sys.executable, "-m", "build"]:
            dist = Path(cwd) / "dist"
            dist.mkdir(exist_ok=True)
            (dist / "antemortem-0.9.4-py3-none-any.whl").write_text(
                "wheel",
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    return runner


def test_release_audit_success_path_with_mocked_subprocesses(tmp_path: Path):
    existing_dist = tmp_path / "dist"
    existing_dist.mkdir()
    (existing_dist / "previous.whl").write_text("keep", encoding="utf-8")
    commands: list[list[str]] = []

    exit_code, summary = release_audit.run_audit(
        tmp_path,
        runner=_success_runner(commands),
    )

    assert exit_code == 0
    assert summary["ok"] is True
    assert len(summary["steps"]) == 11
    assert commands[0] == [sys.executable, "-m", "pip", "install", "-e", ".[dev]"]
    assert commands[-2][:3] == [sys.executable, "-m", "twine"]
    assert commands[-1] == [sys.executable, "scripts/smoke_wheel_install.py"]
    assert (existing_dist / "previous.whl").read_text(encoding="utf-8") == "keep"


def test_release_audit_failure_path_exits_nonzero(tmp_path: Path):
    commands: list[list[str]] = []

    def runner(command, cwd, env, text, capture_output, check, **kwargs):
        commands.append(list(command))
        code = 7 if list(command)[:3] == [sys.executable, "-m", "pytest"] else 0
        return subprocess.CompletedProcess(command, code, stdout="", stderr="")

    exit_code, summary = release_audit.run_audit(tmp_path, runner=runner)

    assert exit_code == 1
    assert summary["ok"] is False
    assert summary["failed_count"] == 1
    assert summary["steps"][-1] == {
        "label": "Run test suite",
        "command": "pytest -q",
        "exit_code": 7,
        "status": "failed",
        "classification": "FAILED",
    }
    assert len(commands) == 2


def test_release_audit_json_output_is_stable(tmp_path: Path):
    commands: list[list[str]] = []

    exit_code, summary = release_audit.run_audit(
        tmp_path,
        json_output=True,
        runner=_success_runner(commands),
    )
    payload = json.loads(json.dumps(summary, sort_keys=True))

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["failed_count"] == 0
    assert payload["steps"][0] == {
        "command": 'python -m pip install -e ".[dev]"',
        "exit_code": 0,
        "label": "Install package and dev dependencies",
        "status": "passed",
        "classification": "PASSED",
    }
    assert payload["steps"][-2]["command"] == "python -m twine check dist/*"
    assert payload["steps"][-1]["command"] == "python scripts/smoke_wheel_install.py"


def test_release_audit_continue_on_error_records_multiple_failures(tmp_path: Path):
    failing_prefixes = {
        (sys.executable, "-m", "pytest"): 3,
        (sys.executable, "scripts/check_repo_consistency.py"): 4,
    }
    commands: list[list[str]] = []

    def runner(command, cwd, env, text, capture_output, check, **kwargs):
        commands.append(list(command))
        if list(command)[:3] == [sys.executable, "-m", "build"]:
            (Path(cwd) / "dist").mkdir(exist_ok=True)
        for prefix, code in failing_prefixes.items():
            if tuple(command[: len(prefix)]) == prefix:
                return subprocess.CompletedProcess(command, code, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    exit_code, summary = release_audit.run_audit(
        tmp_path,
        continue_on_error=True,
        runner=runner,
    )

    failed = [step for step in summary["steps"] if step["status"] == "failed"]
    assert exit_code == 1
    assert summary["failed_count"] == 2
    assert [step["command"] for step in failed] == [
        "pytest -q",
        "python scripts/check_repo_consistency.py",
    ]
    assert len(commands) == 11


def test_release_audit_json_classifies_environment_blocked_packaging(tmp_path: Path):
    commands: list[list[str]] = []

    def runner(command, cwd, env, text, capture_output, check, **kwargs):
        commands.append(list(command))
        if list(command)[:4] == [sys.executable, "-m", "pip", "install"]:
            return subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr=(
                    "Failed to establish a new connection: "
                    "[WinError 10013] socket access forbidden"
                ),
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    exit_code, summary = release_audit.run_audit(
        tmp_path,
        json_output=True,
        runner=runner,
    )

    assert exit_code == 1
    assert summary["ok"] is False
    assert summary["steps"] == [
        {
            "label": "Install package and dev dependencies",
            "command": 'python -m pip install -e ".[dev]"',
            "exit_code": 1,
            "status": "failed",
            "classification": "ENVIRONMENT_BLOCKED",
        }
    ]
    assert len(commands) == 1
