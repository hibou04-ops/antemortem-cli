"""Tests for the wheel-install smoke test."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke_wheel_install.py"
SPEC = importlib.util.spec_from_file_location("smoke_wheel_install", SCRIPT_PATH)
assert SPEC is not None
smoke_wheel_install = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = smoke_wheel_install
SPEC.loader.exec_module(smoke_wheel_install)


def _write_fixture_root(root: Path, *, document_boundary: bool = True, version: str = "0.9.4") -> None:
    (root / "pyproject.toml").write_text(
        f"""\
[project]
name = "antemortem"
version = "{version}"
""",
        encoding="utf-8",
    )
    (root / "examples").mkdir()
    (root / "examples" / "demo_recon.md").write_text("# demo\n", encoding="utf-8")
    case = root / "benchmarks" / "golden_cases" / "case_real"
    case.mkdir(parents=True)
    (case / "README.md").write_text("# case\n", encoding="utf-8")
    (root / "docs").mkdir()
    text = (
        "The wheel smoke test treats examples/ and benchmarks/ as "
        "repository fixtures, not wheel package data.\n"
        if document_boundary
        else "Wheel smoke docs.\n"
    )
    (root / "docs" / "release_hygiene.md").write_text(text, encoding="utf-8")


def _write_wheel(path: Path, *, include_package: bool = True, version: str = "0.9.4") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        if include_package:
            archive.writestr("antemortem/__init__.py", "")
            archive.writestr("antemortem/cli.py", "")
        archive.writestr(
            f"antemortem-{version}.dist-info/METADATA",
            f"Name: antemortem\nVersion: {version}\n",
        )
        archive.writestr(
            f"antemortem-{version}.dist-info/entry_points.txt",
            "[console_scripts]\nantemortem = antemortem.cli:app\n",
        )


def _runner(
    commands: list[list[str]],
    *,
    failures: dict[str, int] | None = None,
    version_stdout: str = "antemortem 0.9.4\n",
    include_package: bool = True,
):
    failures = failures or {}

    def runner(command, cwd, env, text, encoding, errors, capture_output, check):
        commands.append(list(command))
        if list(command)[:3] == [sys.executable, "-m", "build"]:
            outdir = Path(command[command.index("--outdir") + 1])
            outdir.mkdir(parents=True, exist_ok=True)
            _write_wheel(
                outdir / "antemortem-0.9.4-py3-none-any.whl",
                include_package=include_package,
            )
        display = " ".join(str(part) for part in command)
        for needle, code in failures.items():
            if needle in display:
                return subprocess.CompletedProcess(command, code, stdout="", stderr="")
        if "--version" in display:
            return subprocess.CompletedProcess(command, 0, stdout=version_stdout, stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    return runner


def test_smoke_wheel_install_success_path_with_mocked_subprocesses(tmp_path: Path):
    _write_fixture_root(tmp_path)
    commands: list[list[str]] = []
    venv_calls: list[dict[str, object]] = []

    def venv_creator(path, **kwargs):
        venv_calls.append({"path": path, **kwargs})

    exit_code, results = smoke_wheel_install.run_smoke(
        tmp_path,
        runner=_runner(commands),
        venv_creator=venv_creator,
        module_available=lambda _name: True,
    )

    assert exit_code == 0
    assert [result.status for result in results] == [
        "passed",
        "passed",
        "warn",
        "passed",
        "passed",
        "passed",
        "passed",
        "passed",
    ]
    assert results[2].label == "Verify fixture packaging boundary"
    assert "repository-only policy" in results[2].message
    assert commands[0][:5] == [sys.executable, "-m", "build", "--wheel", "--no-isolation"]
    assert "--no-index" in commands[1]
    assert "--no-deps" in commands[1]
    assert commands[-2][1:] == ["doctor", "examples/demo_recon.md", "--repo", ".", "--json"]
    assert commands[-1][1:] == ["eval", "benchmarks/golden_cases", "--json"]
    assert len(venv_calls) == 1
    assert venv_calls[0]["with_pip"] is True
    assert venv_calls[0]["system_site_packages"] is False
    assert venv_calls[0]["clear"] is True


def test_smoke_wheel_install_build_failure_stops(tmp_path: Path):
    _write_fixture_root(tmp_path)
    commands: list[list[str]] = []

    exit_code, results = smoke_wheel_install.run_smoke(
        tmp_path,
        runner=_runner(commands, failures={" -m build ": 8}),
        venv_creator=lambda *args, **kwargs: None,
        module_available=lambda _name: True,
    )

    assert exit_code == 1
    assert results == [
        smoke_wheel_install.StepResult(
            "Build wheel",
            "python -m build --wheel --no-isolation --outdir <tmp>/wheelhouse",
            8,
            "failed",
        )
    ]
    assert len(commands) == 1


def test_smoke_wheel_install_missing_fixture_fails_clearly(tmp_path: Path):
    (tmp_path / "benchmarks" / "golden_cases").mkdir(parents=True)
    (tmp_path / "benchmarks" / "golden_cases" / "case").mkdir()

    exit_code, results = smoke_wheel_install.run_smoke(
        tmp_path,
        runner=_runner([]),
        venv_creator=lambda *args, **kwargs: None,
        module_available=lambda _name: True,
    )

    assert exit_code == 1
    assert results[0].status == "failed"
    assert "examples/demo_recon.md" in results[0].message


def test_smoke_wheel_install_requires_fixture_boundary_documentation(tmp_path: Path):
    _write_fixture_root(tmp_path, document_boundary=False)
    commands: list[list[str]] = []

    exit_code, results = smoke_wheel_install.run_smoke(
        tmp_path,
        runner=_runner(commands),
        venv_creator=lambda *args, **kwargs: None,
        module_available=lambda _name: True,
    )

    assert exit_code == 1
    assert results[-1].label == "Verify fixture packaging boundary"
    assert "repository fixtures, not wheel package data" in results[-1].message
    assert len(commands) == 1


def test_smoke_wheel_install_missing_package_module_still_fails(tmp_path: Path):
    _write_fixture_root(tmp_path)
    commands: list[list[str]] = []

    exit_code, results = smoke_wheel_install.run_smoke(
        tmp_path,
        runner=_runner(commands, include_package=False),
        venv_creator=lambda *args, **kwargs: None,
        module_available=lambda _name: True,
    )

    assert exit_code == 1
    assert results[-1].label == "Verify wheel package contents"
    assert "missing the antemortem package modules" in results[-1].message
    assert len(commands) == 1


def test_smoke_wheel_install_installed_cli_failure_still_fails(tmp_path: Path):
    _write_fixture_root(tmp_path)
    commands: list[list[str]] = []

    exit_code, results = smoke_wheel_install.run_smoke(
        tmp_path,
        runner=_runner(commands, failures={"--help": 7}),
        venv_creator=lambda *args, **kwargs: None,
        module_available=lambda _name: True,
    )

    assert exit_code == 1
    assert results[-1].label == "Run installed help command"
    assert results[-1].status == "failed"


def test_smoke_wheel_install_version_mismatch_still_fails(tmp_path: Path):
    _write_fixture_root(tmp_path)
    commands: list[list[str]] = []

    exit_code, results = smoke_wheel_install.run_smoke(
        tmp_path,
        runner=_runner(commands, version_stdout="antemortem 0.9.3\n"),
        venv_creator=lambda *args, **kwargs: None,
        module_available=lambda _name: True,
    )

    assert exit_code == 1
    assert results[-1].label == "Run installed version command"
    assert "expected version 0.9.4" in results[-1].message


def test_smoke_wheel_install_reports_missing_build_module(tmp_path: Path):
    _write_fixture_root(tmp_path)

    exit_code, results = smoke_wheel_install.run_smoke(
        tmp_path,
        runner=_runner([]),
        venv_creator=lambda *args, **kwargs: None,
        module_available=lambda name: name != "build",
    )

    assert exit_code == 1
    assert results[0].label == "Verify packaging tooling"
    assert results[0].status == "TOOLING_MISSING"
    assert "build:" in results[0].message


def test_smoke_wheel_install_reports_missing_twine_module(tmp_path: Path):
    _write_fixture_root(tmp_path)

    exit_code, results = smoke_wheel_install.run_smoke(
        tmp_path,
        runner=_runner([]),
        venv_creator=lambda *args, **kwargs: None,
        module_available=lambda name: name != "twine",
    )

    assert exit_code == 1
    assert results[0].status == "TOOLING_MISSING"
    assert "twine:" in results[0].message


def test_smoke_wheel_install_reports_missing_hatchling_backend(tmp_path: Path):
    _write_fixture_root(tmp_path)

    exit_code, results = smoke_wheel_install.run_smoke(
        tmp_path,
        runner=_runner([]),
        venv_creator=lambda *args, **kwargs: None,
        module_available=lambda name: name != "hatchling",
    )

    assert exit_code == 1
    assert results[0].status == "TOOLING_MISSING"
    assert "hatchling:" in results[0].message
