# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Run the local release-readiness audit.

This command never uploads artifacts. It runs local verification commands,
builds distribution files into an isolated `dist/` directory, checks them with
twine, then restores any pre-existing `dist/` directory.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class Step:
    label: str
    command: tuple[str, ...]
    display_command: str
    needs_dist_isolation: bool = False
    dynamic_command: bool = False


@dataclass(frozen=True)
class StepResult:
    label: str
    command: str
    exit_code: int
    status: str
    classification: str

    def as_json(self) -> dict[str, object]:
        return {
            "label": self.label,
            "command": self.command,
            "exit_code": self.exit_code,
            "status": self.status,
            "classification": self.classification,
        }


def build_steps() -> tuple[Step, ...]:
    """Return the release audit command sequence in execution order."""
    return (
        Step(
            "Install package and dev dependencies",
            (sys.executable, "-m", "pip", "install", "-e", ".[dev]"),
            'python -m pip install -e ".[dev]"',
        ),
        Step("Run test suite", (sys.executable, "-m", "pytest", "-q"), "pytest -q"),
        Step(
            "Check repository consistency",
            (sys.executable, "scripts/check_repo_consistency.py"),
            "python scripts/check_repo_consistency.py",
        ),
        Step(
            "Check generated README claims",
            (sys.executable, "scripts/generate_readme_claims.py", "--check"),
            "python scripts/generate_readme_claims.py --check",
        ),
        Step(
            "Check public claim ledger",
            (sys.executable, "scripts/check_claim_ledger.py"),
            "python scripts/check_claim_ledger.py",
        ),
        Step(
            "Run offline golden benchmark",
            ("antemortem", "eval", "benchmarks/golden_cases", "--json"),
            "antemortem eval benchmarks/golden_cases --json",
        ),
        Step(
            "Show CLI help",
            (sys.executable, "-m", "antemortem.cli", "--help"),
            "python -m antemortem.cli --help",
        ),
        Step("Show package version", ("antemortem", "--version"), "antemortem --version"),
        Step(
            "Build distribution artifacts",
            (sys.executable, "-m", "build"),
            "python -m build",
            needs_dist_isolation=True,
        ),
        Step(
            "Validate distribution metadata",
            (sys.executable, "-m", "twine", "check", "dist/*"),
            "python -m twine check dist/*",
            needs_dist_isolation=True,
            dynamic_command=True,
        ),
        Step(
            "Smoke-test installed wheel",
            (sys.executable, "scripts/smoke_wheel_install.py"),
            "python scripts/smoke_wheel_install.py",
        ),
    )


def run_audit(
    root: Path,
    *,
    continue_on_error: bool = False,
    json_output: bool = False,
    runner: Runner = subprocess.run,
) -> tuple[int, dict[str, object]]:
    """Run the release audit and return ``(exit_code, summary)``."""
    root = root.resolve()
    env = _audit_env(root)
    results: list[StepResult] = []
    failures = 0

    with _DistIsolation(root):
        for step in build_steps():
            command = _resolve_command(step, root)
            completed = _run_step(step, command, root, env, runner, quiet=json_output)
            status = "passed" if completed.returncode == 0 else "failed"
            classification = _classify_result(step, completed)
            result = StepResult(
                label=step.label,
                command=step.display_command,
                exit_code=completed.returncode,
                status=status,
                classification=classification,
            )
            results.append(result)
            if completed.returncode != 0:
                failures += 1
                if not json_output:
                    print(
                        f"FAILED: {step.display_command} "
                        f"(exit code {completed.returncode}, classification {classification})",
                        file=sys.stderr,
                    )
                if not continue_on_error:
                    break

    summary = {
        "ok": failures == 0,
        "continue_on_error": continue_on_error,
        "failed_count": failures,
        "steps": [result.as_json() for result in results],
    }
    return (0 if failures == 0 else 1), summary


def _run_step(
    step: Step,
    command: Sequence[str],
    root: Path,
    env: dict[str, str],
    runner: Runner,
    *,
    quiet: bool,
) -> subprocess.CompletedProcess[str]:
    if not quiet:
        print(f"\n==> {step.label}")
        print(f"$ {step.display_command}")
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
            print(
                completed.stderr,
                end="" if completed.stderr.endswith("\n") else "\n",
                file=sys.stderr,
            )
    return completed


def _classify_result(step: Step, completed: subprocess.CompletedProcess[str]) -> str:
    if completed.returncode == 0:
        return "PASSED"
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    lowered = output.lower()
    tooling_markers = (
        "no module named build",
        "no module named twine",
        "no module named hatchling",
        "tooling_missing",
        "missing packaging verification tooling",
    )
    if any(marker in lowered for marker in tooling_markers):
        return "TOOLING_MISSING"
    environment_markers = (
        "failed to establish a new connection",
        "failed to fetch",
        "network disabled",
        "winerror 10013",
        "os error 10013",
        "socket",
        "environment_blocked",
    )
    if any(marker in lowered for marker in environment_markers):
        return "ENVIRONMENT_BLOCKED"
    packaging_commands = (
        "python -m pip install -e",
        "python -m build",
        "python -m twine check",
        "python scripts/smoke_wheel_install.py",
    )
    if any(step.display_command.startswith(command) for command in packaging_commands):
        return "PACKAGING_FAILED"
    return "FAILED"


def _resolve_command(step: Step, root: Path) -> tuple[str, ...]:
    if not step.dynamic_command:
        return step.command
    if step.display_command == "python -m twine check dist/*":
        artifacts = sorted(str(path) for path in (root / "dist").glob("*"))
        return (sys.executable, "-m", "twine", "check", *(artifacts or ["dist/*"]))
    return step.command


def _audit_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    src = str(root / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not existing else src + os.pathsep + existing
    return env


class _DistIsolation:
    """Temporarily move existing ``dist`` away and restore it after audit."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.dist = self.root / "dist"
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        self._backup: Path | None = None

    def __enter__(self) -> "_DistIsolation":
        _assert_child_or_equal(self.dist, self.root)
        self._tmp = tempfile.TemporaryDirectory(prefix="release-audit-", dir=self.root)
        backup = Path(self._tmp.name) / "dist.backup"
        if self.dist.exists():
            shutil.move(str(self.dist), str(backup))
            self._backup = backup
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _assert_child_or_equal(self.dist, self.root)
        if self.dist.exists():
            if self.dist.is_dir():
                shutil.rmtree(self.dist)
            else:
                self.dist.unlink()
        if self._backup is not None and self._backup.exists():
            shutil.move(str(self._backup), str(self.dist))
        if self._tmp is not None:
            self._tmp.cleanup()


def _assert_child_or_equal(path: Path, root: Path) -> None:
    resolved_path = path.resolve() if path.exists() else path.absolute()
    resolved_root = root.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise RuntimeError(f"refusing to touch path outside repo: {resolved_path}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Run every step and report all failures instead of stopping at the first.",
    )
    parser.add_argument("--json", action="store_true", help="Print a stable JSON summary.")
    args = parser.parse_args(argv)

    exit_code, summary = run_audit(
        args.root,
        continue_on_error=args.continue_on_error,
        json_output=args.json,
    )
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif exit_code == 0:
        print("\nRelease audit passed.")
    else:
        print("\nRelease audit failed.", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
