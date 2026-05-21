# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Smoke-test the built wheel in a temporary virtual environment.

The test is intentionally local. It builds a wheel without build isolation,
installs that wheel into a temporary virtual environment without contacting a
package index, then runs core CLI commands through the installed entrypoint.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import site
import subprocess
import sys
import tempfile
import tomllib
import venv
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


Runner = Callable[..., subprocess.CompletedProcess[str]]
VenvCreator = Callable[..., None]
ModuleChecker = Callable[[str], bool]

FIXTURE_DOC_MARKER = "repository fixtures, not wheel package data"
PASS = "passed"
WARN = "warn"
FAIL = "failed"
TOOLING_MISSING = "TOOLING_MISSING"
ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"
REQUIRED_TOOLING = {
    "build": "needed for `python -m build --wheel --no-isolation`",
    "twine": "needed for final `python -m twine check dist/*` verification",
    "hatchling": "needed by the hatchling build backend during no-isolation wheel smoke",
}


@dataclass(frozen=True)
class StepResult:
    label: str
    command: str
    exit_code: int
    status: str
    message: str = ""


def run_smoke(
    root: Path,
    *,
    runner: Runner = subprocess.run,
    venv_creator: VenvCreator = venv.create,
    module_available: ModuleChecker | None = None,
) -> tuple[int, list[StepResult]]:
    """Run the wheel smoke test and return ``(exit_code, step_results)``."""
    root = root.resolve()
    expected_version = _load_version(root)
    tooling_error = _check_packaging_tooling(module_available or _module_available)
    if tooling_error:
        return (
            1,
            [
                StepResult(
                    "Verify packaging tooling",
                    "import build, twine, hatchling",
                    1,
                    TOOLING_MISSING,
                    tooling_error,
                )
            ],
        )

    preflight_error = _check_repo_fixtures(root)
    if preflight_error:
        return (
            1,
            [
                StepResult(
                    "Verify smoke fixtures",
                    "internal fixture check",
                    1,
                    FAIL,
                    preflight_error,
                )
            ],
        )

    results: list[StepResult] = []
    with tempfile.TemporaryDirectory(prefix="antemortem-wheel-smoke-") as tmp:
        tmp_root = Path(tmp)
        wheelhouse = tmp_root / "wheelhouse"
        venv_dir = tmp_root / "venv"
        wheelhouse.mkdir()

        build_command = (
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(wheelhouse),
        )
        build = _run_command(
            "Build wheel",
            build_command,
            root,
            runner,
            display_command="python -m build --wheel --no-isolation --outdir <tmp>/wheelhouse",
        )
        results.append(build)
        if build.exit_code != 0:
            return 1, results

        wheel_error = _find_wheel_error(wheelhouse)
        if wheel_error:
            results.append(
                StepResult("Locate built wheel", "find <tmp>/wheelhouse/*.whl", 1, FAIL, wheel_error)
            )
            return 1, results
        wheel = next(wheelhouse.glob("*.whl"))

        package_error = _check_wheel_package_contents(wheel, expected_version)
        if package_error:
            results.append(
                StepResult(
                    "Verify wheel package contents",
                    f"inspect {wheel.name}",
                    1,
                    FAIL,
                    package_error,
                )
            )
            return 1, results
        results.append(
            StepResult(
                "Verify wheel package contents",
                f"inspect {wheel.name}",
                0,
                PASS,
                "wheel contains antemortem package modules, metadata, and console entry point",
            )
        )

        boundary = _check_fixture_packaging_boundary(root, wheel)
        results.append(boundary)
        if boundary.exit_code != 0:
            return 1, results

        venv_creator(str(venv_dir), with_pip=True, system_site_packages=False, clear=True)
        _write_dependency_path_file(venv_dir)
        python_exe = _venv_python(venv_dir)
        antemortem_exe = _venv_script(venv_dir, "antemortem")

        commands: tuple[tuple[str, tuple[str, ...], str], ...] = (
            (
                "Install wheel",
                (
                    str(python_exe),
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--no-deps",
                    "--force-reinstall",
                    str(wheel),
                ),
                "python -m pip install --no-index --no-deps --force-reinstall <wheel>",
            ),
            ("Run installed version command", (str(antemortem_exe), "--version"), "antemortem --version"),
            ("Run installed help command", (str(antemortem_exe), "--help"), "antemortem --help"),
            (
                "Run installed doctor command",
                (
                    str(antemortem_exe),
                    "doctor",
                    "examples/demo_recon.md",
                    "--repo",
                    ".",
                    "--json",
                ),
                "antemortem doctor examples/demo_recon.md --repo . --json",
            ),
            (
                "Run installed eval command",
                (str(antemortem_exe), "eval", "benchmarks/golden_cases", "--json"),
                "antemortem eval benchmarks/golden_cases --json",
            ),
        )
        for label, command, display in commands:
            expected_stdout = expected_version if label == "Run installed version command" else None
            result = _run_command(
                label,
                command,
                root,
                runner,
                display_command=display,
                expected_stdout=expected_stdout,
            )
            results.append(result)
            if result.exit_code != 0:
                return 1, results

    return 0, results


def _run_command(
    label: str,
    command: Sequence[str],
    root: Path,
    runner: Runner,
    *,
    display_command: str,
    expected_stdout: str | None = None,
) -> StepResult:
    print(f"\n==> {label}")
    print(f"$ {display_command}")
    env = _smoke_env()
    try:
        completed = runner(
            list(command),
            cwd=root,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return StepResult(label, display_command, 1, FAIL, f"command executable not found: {exc}")
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n", file=sys.stderr)
    status = PASS if completed.returncode == 0 else FAIL
    if completed.returncode != 0:
        combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        blocked = _classify_environment_block(combined)
        if blocked:
            return StepResult(label, display_command, completed.returncode, blocked, combined.strip())
    if completed.returncode == 0 and expected_stdout and expected_stdout not in completed.stdout:
        return StepResult(
            label,
            display_command,
            1,
            FAIL,
            f"stdout did not contain expected version {expected_stdout}",
        )
    return StepResult(label, display_command, completed.returncode, status)


def _check_packaging_tooling(module_available: ModuleChecker) -> str:
    missing = [name for name in REQUIRED_TOOLING if not module_available(name)]
    if not missing:
        return ""
    details = "; ".join(f"{name}: {REQUIRED_TOOLING[name]}" for name in missing)
    return (
        "missing packaging verification tooling: "
        f"{details}. Run `python -m pip install -e \".[dev]\"` in a network-enabled "
        "environment, then rerun `python scripts/smoke_wheel_install.py`."
    )


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _classify_environment_block(output: str) -> str:
    lowered = output.lower()
    tooling_markers = (
        "no module named build",
        "no module named twine",
        "no module named hatchling",
    )
    if any(marker in lowered for marker in tooling_markers):
        return TOOLING_MISSING
    environment_markers = (
        "failed to establish a new connection",
        "failed to fetch",
        "network disabled",
        "winerror 10013",
        "os error 10013",
        "socket",
    )
    if any(marker in lowered for marker in environment_markers):
        return ENVIRONMENT_BLOCKED
    return ""


def _load_version(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return ""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return str(data.get("project", {}).get("version", ""))


def _check_repo_fixtures(root: Path) -> str:
    required = (
        root / "examples" / "demo_recon.md",
        root / "benchmarks" / "golden_cases",
    )
    missing = [path.relative_to(root).as_posix() for path in required if not path.exists()]
    if missing:
        return "missing required smoke fixture(s): " + ", ".join(missing)
    if not any((root / "benchmarks" / "golden_cases").iterdir()):
        return "missing required smoke fixture cases under benchmarks/golden_cases"
    return ""


def _check_fixture_packaging_boundary(root: Path, wheel: Path) -> StepResult:
    """Verify fixture data is packaged or explicitly documented as external."""
    names = _wheel_names(wheel)
    includes_examples = any(name.startswith("examples/") for name in names)
    includes_benchmarks = any(name.startswith("benchmarks/") for name in names)
    if includes_examples and includes_benchmarks:
        return StepResult(
            "Verify fixture packaging boundary",
            f"inspect {wheel.name}",
            0,
            PASS,
            "wheel includes examples/ and benchmarks/ fixtures",
        )

    docs = root / "docs" / "release_hygiene.md"
    if not docs.exists():
        return StepResult(
            "Verify fixture packaging boundary",
            f"inspect {wheel.name}",
            1,
            FAIL,
            "wheel does not include examples/ and benchmarks/ fixtures, and docs/release_hygiene.md is missing",
        )
    text = docs.read_text(encoding="utf-8")
    if FIXTURE_DOC_MARKER not in text:
        return StepResult(
            "Verify fixture packaging boundary",
            f"inspect {wheel.name}",
            1,
            FAIL,
            "wheel does not include examples/ and benchmarks/ fixtures; "
            f"document them as {FIXTURE_DOC_MARKER!r}",
        )
    return StepResult(
        "Verify fixture packaging boundary",
        f"inspect {wheel.name}",
        0,
        WARN,
        "examples/ and benchmarks/ are absent from the wheel by documented repository-only policy",
    )


def _check_wheel_package_contents(wheel: Path, expected_version: str) -> str:
    names = _wheel_names(wheel)
    if not any(name.startswith("antemortem/") for name in names):
        return "wheel is missing the antemortem package modules"
    if "antemortem/__init__.py" not in names:
        return "wheel is missing antemortem/__init__.py"
    metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
    if not metadata_names:
        return "wheel is missing dist-info/METADATA"
    entry_point_names = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
    if not entry_point_names:
        return "wheel is missing console script metadata entry_points.txt"
    with zipfile.ZipFile(wheel) as archive:
        metadata = archive.read(metadata_names[0]).decode("utf-8", errors="replace")
        entry_points = archive.read(entry_point_names[0]).decode("utf-8", errors="replace")
    if "antemortem" not in entry_points or "antemortem.cli" not in entry_points:
        return "wheel console script metadata does not expose the antemortem CLI entry point"
    if expected_version and f"Version: {expected_version}" not in metadata:
        return f"wheel metadata version does not match pyproject version {expected_version}"
    return ""


def _wheel_names(wheel: Path) -> set[str]:
    try:
        with zipfile.ZipFile(wheel) as archive:
            return set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"built wheel is not a valid zip archive: {wheel}") from exc


def _find_wheel_error(wheelhouse: Path) -> str:
    wheels = sorted(wheelhouse.glob("*.whl"))
    if not wheels:
        return "build completed but produced no wheel"
    if len(wheels) > 1:
        names = ", ".join(path.name for path in wheels)
        return f"build produced multiple wheels; expected exactly one: {names}"
    return ""


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_script(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def _write_dependency_path_file(venv_dir: Path) -> None:
    """Expose already-installed dependencies to the temp venv without pip network access."""
    site_packages = _venv_site_packages(venv_dir)
    site_packages.mkdir(parents=True, exist_ok=True)
    dependency_paths = [
        path
        for path in _current_dependency_paths()
        if path.resolve() != site_packages.resolve()
    ]
    if dependency_paths:
        payload = "\n".join(str(path) for path in dependency_paths) + "\n"
        (site_packages / "zz-antemortem-smoke-deps.pth").write_text(payload, encoding="utf-8")


def _venv_site_packages(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Lib" / "site-packages"
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return venv_dir / "lib" / version / "site-packages"


def _current_dependency_paths() -> tuple[Path, ...]:
    candidates: list[str] = []
    try:
        candidates.extend(site.getsitepackages())
    except AttributeError:
        pass
    try:
        candidates.append(site.getusersitepackages())
    except AttributeError:
        pass
    paths = []
    for raw in candidates:
        path = Path(raw)
        if path.exists() and path.is_dir():
            paths.append(path)
    return tuple(dict.fromkeys(paths))


def _smoke_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("PYTHONPATH", None)
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)

    exit_code, results = run_smoke(args.root)
    for result in results:
        if result.status == WARN:
            print(f"WARN: {result.command} - {result.message}")
            continue
        if result.status != PASS:
            print(
                f"{result.status}: {result.command} (exit code {result.exit_code})",
                file=sys.stderr,
            )
            if result.message:
                print(result.message, file=sys.stderr)
            break
    if exit_code == 0:
        print("\nWheel smoke test passed.")
    else:
        print("\nWheel smoke test failed.", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
