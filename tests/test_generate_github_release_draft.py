"""Tests for GitHub Release draft generation."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "generate_github_release_draft.py"
SPEC = importlib.util.spec_from_file_location("generate_github_release_draft", SCRIPT_PATH)
assert SPEC is not None
generate_github_release_draft = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = generate_github_release_draft
SPEC.loader.exec_module(generate_github_release_draft)


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
        """\
# Changelog

## [1.2.3] - 2026-05-22

### Added

- Added release draft generation.

### Changed

- Changed packaging verification reporting.

### Fixed

- Fixed blocked packaging checks being easy to miss.
""",
        encoding="utf-8",
    )


def _benchmark_json() -> str:
    return json.dumps(
        {
            "metrics": {
                "decision_accuracy": 1.0,
                "citation_valid_rate": 0.75,
            },
            "totals": {
                "cases": 4,
                "schema_success": 4,
            },
        }
    )


def _runner(
    commands: list[list[str]],
    *,
    blocked_build: bool = False,
    release_audit_blocked: bool = False,
):
    def runner(command, cwd, env, text, encoding, errors, capture_output, check):
        command = list(command)
        commands.append(command)
        if command[:3] == [sys.executable, "-m", "pytest"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == [sys.executable, "scripts/check_repo_consistency.py"]:
            return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")
        if command == [sys.executable, "scripts/generate_readme_claims.py", "--check"]:
            return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")
        if command[:3] == ["antemortem", "eval", "benchmarks/golden_cases"]:
            return subprocess.CompletedProcess(command, 0, stdout=_benchmark_json(), stderr="")
        if command[:3] == [sys.executable, "-m", "build"]:
            if blocked_build:
                return subprocess.CompletedProcess(
                    command,
                    1,
                    stdout="",
                    stderr="No module named build",
                )
            dist = Path(cwd) / "dist"
            dist.mkdir(exist_ok=True)
            (dist / "antemortem-1.2.3-py3-none-any.whl").write_text("wheel", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:4] == [sys.executable, "-m", "twine", "check"]:
            return subprocess.CompletedProcess(command, 0, stdout="PASSED\n", stderr="")
        if command == [sys.executable, "scripts/smoke_wheel_install.py"]:
            return subprocess.CompletedProcess(command, 0, stdout="Wheel smoke test passed.\n", stderr="")
        if command == [sys.executable, "scripts/release_audit.py", "--json"]:
            if release_audit_blocked:
                return subprocess.CompletedProcess(
                    command,
                    1,
                    stdout=json.dumps(
                        {
                            "ok": False,
                            "failed_count": 1,
                            "steps": [
                                {
                                    "status": "failed",
                                    "classification": "ENVIRONMENT_BLOCKED",
                                }
                            ],
                        }
                    ),
                    stderr="",
                )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"ok": True, "failed_count": 0, "steps": []}),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    return runner


def test_release_draft_renders_changelog_status_and_links(tmp_path: Path):
    _write_repo(tmp_path)
    commands: list[list[str]] = []

    draft = generate_github_release_draft.generate_github_release_draft(
        tmp_path,
        runner=_runner(commands),
    )

    assert draft.startswith("# antemortem 1.2.3")
    assert "- Added release draft generation." in draft
    assert "- Changed packaging verification reporting." in draft
    assert "- Fixed blocked packaging checks being easy to miss." in draft
    assert "| package build | `python -m build` | passed | `PASSED` | `0` |" in draft
    assert "| twine check | `python -m twine check dist/*` | passed | `PASSED` | `0` |" in draft
    assert "| wheel smoke install | `python scripts/smoke_wheel_install.py` | passed | `PASSED` | `0` |" in draft
    assert "`decision_accuracy=1.000`" in draft
    assert "[README](../README.md)" in draft
    assert "[Benchmark-backed claims](../README.md#benchmark-backed-claims)" in draft
    assert "publish-ready" not in draft.lower()


def test_release_draft_marks_packaging_blockers_not_publish_ready(tmp_path: Path):
    _write_repo(tmp_path)
    commands: list[list[str]] = []

    draft = generate_github_release_draft.generate_github_release_draft(
        tmp_path,
        runner=_runner(commands, blocked_build=True, release_audit_blocked=True),
    )

    assert "not publish-ready" in draft
    assert "| package build | `python -m build` | failed | `TOOLING_MISSING` | `1` |" in draft
    assert (
        "| release audit | `python scripts/release_audit.py --json` | failed | "
        "`ENVIRONMENT_BLOCKED` | `1` |"
    ) in draft
    assert "Do not publish until package build" in draft


def test_release_draft_reads_benchmark_metrics_from_json_file(tmp_path: Path):
    _write_repo(tmp_path)
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(_benchmark_json(), encoding="utf-8")
    commands: list[list[str]] = []

    draft = generate_github_release_draft.generate_github_release_draft(
        tmp_path,
        benchmark_json=benchmark_path,
        runner=_runner(commands),
    )

    normalized_benchmark_path = str(benchmark_path).replace("\\", "/")
    assert f"Source: `{normalized_benchmark_path}`" in draft
    assert "`citation_valid_rate=0.750`" in draft
    assert not any(command[:3] == ["antemortem", "eval", "benchmarks/golden_cases"] for command in commands)


def test_main_writes_draft_without_github_api(tmp_path: Path, monkeypatch):
    _write_repo(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(generate_github_release_draft.subprocess, "run", _runner(commands))
    output = tmp_path / "draft.md"

    exit_code = generate_github_release_draft.main(
        [
            "--root",
            str(tmp_path),
            "--version",
            "1.2.3",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    text = output.read_text(encoding="utf-8")
    assert text.startswith("# antemortem 1.2.3")
    assert all(command and command[0] != "gh" for command in commands)
