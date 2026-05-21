# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Verify a published release after upload.

The default path checks PyPI metadata, a GitHub release tag, installs the
published package into a clean virtual environment, then runs offline CLI
commands with provider API key environment variables removed. ``--dry-run`` and
``--skip-network`` never contact PyPI or GitHub and never mark the release as
verified.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import venv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


Runner = Callable[..., subprocess.CompletedProcess[str]]
VenvCreator = Callable[..., None]
JsonFetcher = Callable[[str], dict[str, object]]

API_KEY_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
)

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIPPED = "SKIPPED"
STATUS_PENDING = "PENDING"
STATUS_NOT_RUN = "NOT_RUN"

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[A-Za-z0-9.+-]+)?$")

REQUIRED_DOCS = (
    "docs/post_release_verification.md",
    "docs/download_analytics_note.md",
    "docs/download_analytics_note_kr.md",
)

DOCUMENTED_COMMANDS = (
    "python scripts/post_release_check.py --version",
    "--dry-run",
    "--skip-network",
    "python scripts/check_repo_consistency.py",
    "python scripts/generate_readme_claims.py --check",
)


@dataclass(frozen=True)
class StepResult:
    label: str
    command: str
    exit_code: int
    status: str
    message: str = ""

    def as_json(self) -> dict[str, object]:
        return {
            "label": self.label,
            "command": self.command,
            "exit_code": self.exit_code,
            "status": self.status,
            "message": self.message,
        }


def run_post_release_check(
    root: Path,
    *,
    expected_version: str | None = None,
    skip_network: bool = False,
    dry_run: bool = False,
    skip_pypi_network: bool = False,
    json_output: bool = False,
    runner: Runner = subprocess.run,
    venv_creator: VenvCreator = venv.create,
    fetch_json: JsonFetcher | None = None,
) -> tuple[int, dict[str, object]]:
    """Run post-release verification and return ``(exit_code, summary)``."""
    root = root.resolve()
    fetch_json = fetch_json or _fetch_json
    project = _load_project(root)
    package_name = str(project["name"])
    pyproject_version = str(project["version"])
    expected = expected_version or pyproject_version
    source_url = str(project.get("urls", {}).get("Source") or project.get("urls", {}).get("Repository", ""))
    skip_network = skip_network or skip_pypi_network
    mode = "dry-run" if dry_run else "skip-network" if skip_network else "live"

    results: list[StepResult] = []

    def record(result: StepResult) -> bool:
        results.append(result)
        if not json_output:
            _print_result(result)
        return result.status != STATUS_FAIL

    if not record(_check_expected_version(expected)):
        return _summary(results, expected, mode)
    if not record(
        _check_value(
            "Check pyproject version",
            "read pyproject.toml",
            pyproject_version,
            expected,
            "pyproject version must match the release being verified",
        )
    ):
        return _summary(results, expected, mode)

    if not record(_check_required_docs(root)):
        return _summary(results, expected, mode)
    if not record(_check_documented_command_sequence(root)):
        return _summary(results, expected, mode)
    if not record(_check_readme_version(root, expected)):
        return _summary(results, expected, mode)

    if mode != "live":
        for result in _network_placeholders(mode, package_name, expected, source_url):
            record(result)
        cli_commands = _local_cli_commands(expected)
    else:
        if not record(_check_pypi_version(package_name, expected, fetch_json)):
            return _summary(results, expected, mode)
        if not record(_check_github_release_tag(source_url, expected, root, runner, json_output)):
            return _summary(results, expected, mode)

        env = _post_release_env()
        install_result, cli_commands = _install_from_pypi(
            root,
            package_name,
            expected,
            env,
            runner,
            venv_creator,
            json_output,
        )
        if not record(install_result):
            return _summary(results, expected, mode)

    env = _post_release_env()
    for spec in cli_commands:
        result = _run_command(
            spec["label"],
            spec["command"],
            root,
            env,
            runner,
            display_command=spec["display"],
            quiet=json_output,
            expected_stdout=spec.get("expected_stdout"),
        )
        if not record(result):
            return _summary(results, expected, mode)

    record(
        StepResult(
            "Verify offline commands require no provider API keys",
            "doctor/lint/eval with provider API env vars removed",
            0,
            STATUS_PASS,
            "offline commands completed with provider key variables removed",
        )
    )
    return _summary(results, expected, mode)


def _install_from_pypi(
    root: Path,
    package_name: str,
    expected_version: str,
    env: dict[str, str],
    runner: Runner,
    venv_creator: VenvCreator,
    json_output: bool,
) -> tuple[StepResult, tuple[dict[str, object], ...]]:
    tmp = tempfile.TemporaryDirectory(prefix="antemortem-post-release-")
    venv_dir = Path(tmp.name) / "venv"
    venv_creator(str(venv_dir), with_pip=True, system_site_packages=False, clear=True)
    python_exe = _venv_python(venv_dir)
    antemortem_exe = _venv_script(venv_dir, "antemortem")
    requirement = f"{package_name}=={expected_version}"
    install = _run_command(
        "Install package from PyPI",
        (str(python_exe), "-m", "pip", "install", "--no-cache-dir", requirement),
        root,
        env,
        runner,
        display_command=f"python -m pip install --no-cache-dir {requirement}",
        quiet=json_output,
    )
    if install.status == STATUS_FAIL:
        tmp.cleanup()
        return install, ()

    commands = _installed_cli_commands(antemortem_exe, expected_version)
    # Keep the temp directory alive until process exit. The script is short-lived,
    # and retaining it avoids deleting the installed CLI before later steps run.
    _TEMP_DIRS.append(tmp)
    return install, commands


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


def _installed_cli_commands(antemortem_exe: Path, expected_version: str) -> tuple[dict[str, object], ...]:
    exe = str(antemortem_exe)
    return (
        {
            "label": "Verify installed version command",
            "command": (exe, "--version"),
            "display": "antemortem --version",
            "expected_stdout": expected_version,
        },
        {
            "label": "Verify installed help command",
            "command": (exe, "--help"),
            "display": "antemortem --help",
        },
        {
            "label": "Verify doctor offline",
            "command": (exe, "doctor", "examples/demo_recon.md", "--repo", ".", "--json"),
            "display": "antemortem doctor examples/demo_recon.md --repo . --json",
        },
        {
            "label": "Verify lint offline",
            "command": (exe, "lint", "examples/demo_antemortem.md", "--repo", "."),
            "display": "antemortem lint examples/demo_antemortem.md --repo .",
        },
        {
            "label": "Verify eval offline",
            "command": (exe, "eval", "benchmarks/golden_cases", "--json"),
            "display": "antemortem eval benchmarks/golden_cases --json",
        },
    )


def _local_cli_commands(expected_version: str) -> tuple[dict[str, object], ...]:
    base = (sys.executable, "-m", "antemortem.cli")
    return (
        {
            "label": "Verify local version command",
            "command": (*base, "--version"),
            "display": "python -m antemortem.cli --version",
            "expected_stdout": expected_version,
        },
        {
            "label": "Verify local help command",
            "command": (*base, "--help"),
            "display": "python -m antemortem.cli --help",
        },
        {
            "label": "Verify doctor offline",
            "command": (*base, "doctor", "examples/demo_recon.md", "--repo", ".", "--json"),
            "display": "python -m antemortem.cli doctor examples/demo_recon.md --repo . --json",
        },
        {
            "label": "Verify lint offline",
            "command": (*base, "lint", "examples/demo_antemortem.md", "--repo", "."),
            "display": "python -m antemortem.cli lint examples/demo_antemortem.md --repo .",
        },
        {
            "label": "Verify eval offline",
            "command": (*base, "eval", "benchmarks/golden_cases", "--json"),
            "display": "python -m antemortem.cli eval benchmarks/golden_cases --json",
        },
    )


def _check_expected_version(expected_version: str) -> StepResult:
    if VERSION_RE.match(expected_version):
        return StepResult(
            "Check expected version argument",
            "--version",
            0,
            STATUS_PASS,
            f"{expected_version} is a valid release version",
        )
    return StepResult(
        "Check expected version argument",
        "--version",
        1,
        STATUS_FAIL,
        f"{expected_version!r} is not a valid release version",
    )


def _check_required_docs(root: Path) -> StepResult:
    missing = [rel for rel in REQUIRED_DOCS if not (root / rel).exists()]
    if missing:
        return StepResult(
            "Check post-release docs",
            "docs/post_release_verification.md and analytics notes",
            1,
            STATUS_FAIL,
            "missing local docs: " + ", ".join(missing),
        )
    return StepResult(
        "Check post-release docs",
        "docs/post_release_verification.md and analytics notes",
        0,
        STATUS_PASS,
        "post-release and analytics docs exist",
    )


def _check_documented_command_sequence(root: Path) -> StepResult:
    docs = (root / "docs" / "post_release_verification.md").read_text(encoding="utf-8")
    missing = [needle for needle in DOCUMENTED_COMMANDS if needle not in docs]
    if missing:
        return StepResult(
            "Check documented command sequence",
            "read docs/post_release_verification.md",
            1,
            STATUS_FAIL,
            "post-release command sequence is missing: " + ", ".join(missing),
        )
    return StepResult(
        "Check documented command sequence",
        "read docs/post_release_verification.md",
        0,
        STATUS_PASS,
        "post-release command sequence is documented",
    )


def _check_value(
    label: str,
    command: str,
    actual: str,
    expected: str,
    context: str,
) -> StepResult:
    if actual == expected:
        return StepResult(label, command, 0, STATUS_PASS, f"{actual} matches expected")
    return StepResult(label, command, 1, STATUS_FAIL, f"{context}: got {actual}, expected {expected}")


def _check_readme_version(root: Path, expected_version: str) -> StepResult:
    readme = (root / "README.md").read_text(encoding="utf-8")
    needles = (
        f"Current release: v{expected_version}",
        f"img.shields.io/badge/pypi-{expected_version}-blue.svg",
    )
    missing = [needle for needle in needles if needle not in readme]
    if missing:
        return StepResult(
            "Check README release version",
            "read README.md",
            1,
            STATUS_FAIL,
            "README release/PyPI badge mismatch: " + ", ".join(missing),
        )
    return StepResult(
        "Check README release version",
        "read README.md",
        0,
        STATUS_PASS,
        f"README release and PyPI badge match {expected_version}",
    )


def _network_placeholders(
    mode: str,
    package_name: str,
    expected_version: str,
    source_url: str,
) -> tuple[StepResult, ...]:
    status = STATUS_PENDING if mode == "dry-run" else STATUS_SKIPPED
    reason = (
        "--dry-run does not contact PyPI, GitHub, or remote package indexes"
        if mode == "dry-run"
        else "--skip-network skips PyPI, GitHub, and remote package install checks"
    )
    return (
        StepResult(
            "Check PyPI package version",
            f"GET https://pypi.org/pypi/{package_name}/json",
            0,
            status,
            reason,
        ),
        StepResult(
            "Check GitHub release tag",
            f"git ls-remote --tags --refs {source_url} v{expected_version}",
            0,
            status,
            reason,
        ),
        StepResult(
            "Install package from PyPI",
            f"python -m pip install --no-cache-dir {package_name}=={expected_version}",
            0,
            status,
            reason,
        ),
        StepResult(
            "Verify installed CLI smoke checks",
            "antemortem --version; antemortem --help; doctor; lint; eval",
            0,
            STATUS_NOT_RUN if mode == "dry-run" else STATUS_SKIPPED,
            "requires the remote PyPI install step",
        ),
    )


def _check_pypi_version(
    package_name: str,
    expected_version: str,
    fetch_json: JsonFetcher,
) -> StepResult:
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        payload = fetch_json(url)
        info = payload.get("info", {})
        version = str(info.get("version", ""))
    except Exception as exc:  # pragma: no cover - exact network errors vary
        return StepResult("Check PyPI package version", f"GET {url}", 1, STATUS_FAIL, str(exc))
    if version != expected_version:
        return StepResult(
            "Check PyPI package version",
            f"GET {url}",
            1,
            STATUS_FAIL,
            f"PyPI reports {version}, expected {expected_version}",
        )
    return StepResult(
        "Check PyPI package version",
        f"GET {url}",
        0,
        STATUS_PASS,
        f"PyPI reports {version}",
    )


def _check_github_release_tag(
    source_url: str,
    expected_version: str,
    root: Path,
    runner: Runner,
    quiet: bool,
) -> StepResult:
    tag = f"v{expected_version}"
    command = ("git", "ls-remote", "--tags", "--refs", source_url, tag)
    result = _run_command(
        "Check GitHub release tag",
        command,
        root,
        _post_release_env(),
        runner,
        display_command=f"git ls-remote --tags --refs {source_url} {tag}",
        quiet=quiet,
    )
    if result.status == STATUS_FAIL:
        return result
    completed = getattr(result, "_completed", None)
    stdout = completed.stdout if completed is not None else ""
    if tag not in stdout:
        return StepResult(
            "Check GitHub release tag",
            f"git ls-remote --tags --refs {source_url} {tag}",
            1,
            STATUS_FAIL,
            f"remote tag {tag} was not found",
        )
    return StepResult(
        "Check GitHub release tag",
        f"git ls-remote --tags --refs {source_url} {tag}",
        0,
        STATUS_PASS,
        f"remote tag {tag} exists",
    )


def _run_command(
    label: str,
    command: Sequence[str],
    root: Path,
    env: dict[str, str],
    runner: Runner,
    *,
    display_command: str,
    quiet: bool,
    expected_stdout: str | None = None,
) -> StepResult:
    if not quiet:
        print(f"\n==> {label}")
        print(f"$ {display_command}")
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
    if not quiet:
        if completed.stdout:
            print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
        if completed.stderr:
            print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n", file=sys.stderr)
    status = STATUS_PASS if completed.returncode == 0 else STATUS_FAIL
    message = ""
    exit_code = completed.returncode
    if completed.returncode == 0 and expected_stdout and expected_stdout not in completed.stdout:
        status = STATUS_FAIL
        exit_code = 1
        message = f"stdout did not contain expected version {expected_stdout}"
    result = StepResult(label, display_command, exit_code, status, message)
    object.__setattr__(result, "_completed", completed)
    return result


def _summary(
    results: list[StepResult],
    expected_version: str,
    mode: str,
) -> tuple[int, dict[str, object]]:
    failed = [result for result in results if result.status == STATUS_FAIL]
    pending = [result for result in results if result.status == STATUS_PENDING]
    skipped = [result for result in results if result.status == STATUS_SKIPPED]
    not_run = [result for result in results if result.status == STATUS_NOT_RUN]
    release_verified = not failed and mode == "live" and not pending and not skipped and not not_run
    summary = {
        "ok": not failed,
        "expected_version": expected_version,
        "mode": mode,
        "dry_run": mode == "dry-run",
        "network_allowed": mode == "live",
        "skip_network": mode in {"dry-run", "skip-network"},
        "skip_pypi_network": mode == "skip-network",
        "release_verified": release_verified,
        "failed_count": len(failed),
        "pending_count": len(pending),
        "skipped_count": len(skipped),
        "not_run_count": len(not_run),
        "steps": [result.as_json() for result in results],
    }
    return (0 if not failed else 1), summary


def _print_result(result: StepResult) -> None:
    if result.status in {STATUS_SKIPPED, STATUS_PENDING, STATUS_NOT_RUN}:
        print(f"{result.status}: {result.label} -- {result.message}")
    elif result.status == STATUS_PASS:
        print(f"PASS: {result.label} -- {result.message}")
    else:
        print(f"FAIL: {result.label} -- {result.message}", file=sys.stderr)


def _load_project(root: Path) -> dict[str, object]:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["project"]


def _fetch_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310 - release check URL is fixed by caller.
        return json.loads(response.read().decode("utf-8"))


def _post_release_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env["ANTEMORTEM_ENABLE_LIVE_PROVIDER_TESTS"] = "0"
    for key in API_KEY_ENV_VARS:
        env.pop(key, None)
    return env


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_script(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--version",
        dest="expected_version",
        help="Release version to verify. Defaults to pyproject.toml.",
    )
    parser.add_argument("--json", action="store_true", help="Print a stable JSON summary.")
    parser.add_argument(
        "--skip-network",
        action="store_true",
        help="Skip PyPI, GitHub, and remote install checks. Local offline checks still run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate local post-release readiness without contacting PyPI or GitHub.",
    )
    parser.add_argument(
        "--skip-pypi-network",
        action="store_true",
        help="Deprecated alias for --skip-network.",
    )
    args = parser.parse_args(argv)

    exit_code, summary = run_post_release_check(
        args.root,
        expected_version=args.expected_version,
        skip_network=args.skip_network,
        dry_run=args.dry_run,
        skip_pypi_network=args.skip_pypi_network,
        json_output=args.json,
    )
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif exit_code == 0 and summary.get("release_verified"):
        print("\nPost-release verification passed.")
    elif exit_code == 0:
        print("\nPost-release dry-run checks completed; release is not verified until network checks pass.")
    else:
        print("\nPost-release verification failed.", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
