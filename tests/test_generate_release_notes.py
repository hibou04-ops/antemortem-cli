"""Tests for deterministic release notes generation."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "generate_release_notes.py"
SPEC = importlib.util.spec_from_file_location("generate_release_notes", SCRIPT_PATH)
assert SPEC is not None
generate_release_notes = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = generate_release_notes
SPEC.loader.exec_module(generate_release_notes)


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

- Added deterministic release notes generation.

### Changed

- Changed release hygiene docs.

### Fixed

- Fixed stale release preparation notes.
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


def _runner_with_git(commands: list[list[str]]):
    def runner(command, cwd, env, text, capture_output, check, **kwargs):
        command = list(command)
        commands.append(command)
        if command[:3] == ["git", "diff", "--name-status"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="A\tscripts/generate_release_notes.py\nM\tREADME.md\n",
                stderr="",
            )
        if command[-2:] == ["--exclude-standard"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:3] == [sys.executable, "-m", "antemortem.cli"]:
            return subprocess.CompletedProcess(command, 0, stdout=_benchmark_json(), stderr="")
        if command == [sys.executable, "scripts/check_repo_consistency.py"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="Repository consistency check passed.\n",
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    return runner


def test_release_notes_use_explicit_files_when_git_metadata_is_unavailable(tmp_path: Path):
    _write_repo(tmp_path)
    commands: list[list[str]] = []

    notes = generate_release_notes.generate_release_notes(
        tmp_path,
        explicit_files=("A:scripts/generate_release_notes.py", "M:README.md"),
        runner=_runner_with_git(commands),
    )

    assert "Change source: explicit file input" in notes
    assert "File added: `scripts/generate_release_notes.py`" in notes
    assert "File changed: `README.md`" in notes
    assert not any(command and command[0] == "git" for command in commands)


def test_release_notes_use_git_range_and_changelog_entries(tmp_path: Path):
    _write_repo(tmp_path)
    commands: list[list[str]] = []

    notes = generate_release_notes.generate_release_notes(
        tmp_path,
        from_ref="v1.2.2",
        to_ref="HEAD",
        runner=_runner_with_git(commands),
    )

    assert ["git", "diff", "--name-status", "v1.2.2", "HEAD"] in commands
    assert "- Added deterministic release notes generation." in notes
    assert "- Changed release hygiene docs." in notes
    assert "- Fixed stale release preparation notes." in notes
    assert "Change source: `git diff --name-status v1.2.2 HEAD`" in notes


def test_benchmark_metrics_are_rendered_only_from_json(tmp_path: Path):
    _write_repo(tmp_path)
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(_benchmark_json(), encoding="utf-8")
    commands: list[list[str]] = []

    notes = generate_release_notes.generate_release_notes(
        tmp_path,
        explicit_files=("README.md",),
        benchmark_json=benchmark_path,
        runner=_runner_with_git(commands),
    )

    assert "Benchmark metrics read from generated JSON file" in notes
    assert "`citation_valid_rate=0.750`" in notes
    assert "`decision_accuracy=1.000`" in notes
    assert not any(command[:3] == [sys.executable, "-m", "antemortem.cli"] for command in commands)


def test_main_writes_output_with_supported_flags(tmp_path: Path, monkeypatch):
    _write_repo(tmp_path)
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(_benchmark_json(), encoding="utf-8")
    commands: list[list[str]] = []
    monkeypatch.setattr(generate_release_notes.subprocess, "run", _runner_with_git(commands))
    output = tmp_path / "notes.md"

    exit_code = generate_release_notes.main(
        [
            "--root",
            str(tmp_path),
            "--version",
            "1.2.3",
            "--from",
            "v1.2.2",
            "--to",
            "HEAD",
            "--benchmark-json",
            str(benchmark_path),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    text = output.read_text(encoding="utf-8")
    assert text.startswith("# Release Notes: antemortem 1.2.3")
    assert "## Verification commands" in text
    required_commands = (
        'python -m pip install -e ".[dev]"',
        "pytest -q",
        "python scripts/check_repo_consistency.py",
        "python scripts/generate_readme_claims.py --check",
        "python scripts/release_audit.py",
        "antemortem eval benchmarks/golden_cases --json",
        "python -m build",
        "python -m twine check dist/*",
    )
    for command in required_commands:
        assert f"`{command}`" in text
    assert "`python scripts/check_repo_consistency.py` -> passed (exit `0`)" in text
