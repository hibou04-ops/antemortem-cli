# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Gate whether the repository is ready for a manual publish action.

This script never uploads packages, creates tags, or pushes commits. It only
answers whether the local repository has completed the checks required before a
separate manual publish step.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


Runner = Callable[..., subprocess.CompletedProcess[str]]

PASS = "PASS"
FAIL = "FAIL"
ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"
TOOLING_MISSING = "TOOLING_MISSING"
NETWORK_BLOCKED = "NETWORK_BLOCKED"
GIT_STATE_BLOCKED = "GIT_STATE_BLOCKED"

SECRET_PATTERNS = (
    re.compile(r"\bpypi-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\b(?:PYPI_API_TOKEN|TWINE_PASSWORD|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY)\s*="),
)


@dataclass(frozen=True)
class CheckResult:
    label: str
    command: str
    classification: str
    exit_code: int | None
    message: str
    next_step: str

    def as_json(self) -> dict[str, object]:
        return {
            "label": self.label,
            "command": self.command,
            "classification": self.classification,
            "exit_code": self.exit_code,
            "message": self.message,
            "next": self.next_step,
        }


def run_publish_readiness(
    root: Path,
    *,
    allow_dirty: bool = False,
    skip_git_checks: bool = False,
    continue_on_error: bool = False,
    runner: Runner = subprocess.run,
) -> tuple[int, dict[str, object]]:
    root = root.resolve()
    env = _readiness_env(root)
    version = _load_version(root)
    checks: list[CheckResult] = []
    failures = 0
    build_started_at: float | None = None

    def record(result: CheckResult) -> bool:
        nonlocal failures
        checks.append(result)
        if result.classification != PASS:
            failures += 1
            return continue_on_error
        return True

    static_checks = (
        _check_worktree(root, allow_dirty=allow_dirty, skip_git_checks=skip_git_checks, runner=runner, env=env),
        _check_changelog_version(root, version),
        _check_git_tag_absent(root, version, skip_git_checks=skip_git_checks, runner=runner, env=env),
        _check_existing_dist(root, version),
    )
    for result in static_checks:
        if not record(result):
            return _summary(checks, failures, allow_dirty, skip_git_checks, continue_on_error, version)

    for label, display, command in (
        ("README/generated claims", "python scripts/check_repo_consistency.py", [sys.executable, "scripts/check_repo_consistency.py"]),
        (
            "generated claims check",
            "python scripts/generate_readme_claims.py --check",
            [sys.executable, "scripts/generate_readme_claims.py", "--check"],
        ),
        (
            "golden benchmark eval",
            "antemortem eval benchmarks/golden_cases --json",
            ["antemortem", "eval", "benchmarks/golden_cases", "--json"],
        ),
    ):
        result = _run_command_check(root, label, display, command, runner=runner, env=env)
        if not record(result):
            return _summary(checks, failures, allow_dirty, skip_git_checks, continue_on_error, version)

    build_started_at = time.time()
    build_result = _run_command_check(
        root,
        "package build",
        "python -m build",
        [sys.executable, "-m", "build"],
        runner=runner,
        env=env,
    )
    if not record(build_result):
        return _summary(checks, failures, allow_dirty, skip_git_checks, continue_on_error, version)

    freshness = _check_fresh_artifacts(root, version, build_started_at)
    if not record(freshness):
        return _summary(checks, failures, allow_dirty, skip_git_checks, continue_on_error, version)

    twine_command = _twine_command(root)
    for label, display, command in (
        ("twine check", "python -m twine check dist/*", twine_command),
        (
            "wheel smoke install",
            "python scripts/smoke_wheel_install.py",
            [sys.executable, "scripts/smoke_wheel_install.py"],
        ),
        (
            "release audit",
            "python scripts/release_audit.py",
            [sys.executable, "scripts/release_audit.py"],
        ),
    ):
        result = _run_command_check(root, label, display, command, runner=runner, env=env)
        if not record(result):
            return _summary(checks, failures, allow_dirty, skip_git_checks, continue_on_error, version)

    return _summary(checks, failures, allow_dirty, skip_git_checks, continue_on_error, version)


def _check_worktree(
    root: Path,
    *,
    allow_dirty: bool,
    skip_git_checks: bool,
    runner: Runner,
    env: dict[str, str],
) -> CheckResult:
    if skip_git_checks:
        return CheckResult(
            "working tree",
            "git status --porcelain",
            PASS,
            0,
            "git checks skipped by explicit option",
            "do not use --skip-git-checks for final publish approval",
        )
    if allow_dirty:
        return CheckResult(
            "working tree",
            "git status --porcelain",
            PASS,
            0,
            "dirty working tree allowed by explicit option",
            "omit --allow-dirty for final publish approval",
        )
    completed = _run_raw(
        root,
        ["git", "-c", f"safe.directory={root.as_posix()}", "status", "--porcelain"],
        runner,
        env,
    )
    if completed.returncode != 0:
        return CheckResult(
            "working tree",
            "git status --porcelain",
            GIT_STATE_BLOCKED,
            completed.returncode,
            "git status could not be read",
            "fix git safe.directory/permissions or use --skip-git-checks only for local diagnostics",
        )
    if completed.stdout.strip():
        return CheckResult(
            "working tree",
            "git status --porcelain",
            GIT_STATE_BLOCKED,
            1,
            "uncommitted changes are present",
            "commit or stash changes, or pass --allow-dirty for a non-final local run",
        )
    return CheckResult("working tree", "git status --porcelain", PASS, 0, "working tree is clean", "none")


def _check_changelog_version(root: Path, version: str) -> CheckResult:
    path = root / "CHANGELOG.md"
    if not path.exists():
        return CheckResult("CHANGELOG version", "CHANGELOG.md", FAIL, 1, "CHANGELOG.md is missing", "add a section for the current pyproject version")
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^##\s+\[?v?{re.escape(version)}\]?(?:\s+-\s+.*)?$", re.M)
    if not pattern.search(text):
        return CheckResult(
            "CHANGELOG version",
            "CHANGELOG.md",
            FAIL,
            1,
            f"CHANGELOG.md has no section for `{version}`",
            f"add `## [{version}] - YYYY-MM-DD` before publishing",
        )
    return CheckResult("CHANGELOG version", "CHANGELOG.md", PASS, 0, f"CHANGELOG.md has a `{version}` section", "none")


def _check_git_tag_absent(
    root: Path,
    version: str,
    *,
    skip_git_checks: bool,
    runner: Runner,
    env: dict[str, str],
) -> CheckResult:
    if skip_git_checks:
        return CheckResult("git tag", f"git rev-parse refs/tags/v{version}", PASS, 0, "git tag check skipped by explicit option", "do not use --skip-git-checks for final publish approval")
    candidates = (f"refs/tags/v{version}", f"refs/tags/{version}")
    existing: list[str] = []
    for ref in candidates:
        completed = _run_raw(
            root,
            ["git", "-c", f"safe.directory={root.as_posix()}", "rev-parse", "--verify", "--quiet", ref],
            runner,
            env,
        )
        if completed.returncode == 0:
            existing.append(ref.removeprefix("refs/tags/"))
        elif completed.returncode not in {1}:
            return CheckResult(
                "git tag",
                "git rev-parse --verify refs/tags/<version>",
                GIT_STATE_BLOCKED,
                completed.returncode,
                "git tag state could not be read",
                "fix git permissions before publishing",
            )
    if existing:
        return CheckResult(
            "git tag",
            "git rev-parse --verify refs/tags/<version>",
            GIT_STATE_BLOCKED,
            1,
            "release tag already exists: " + ", ".join(existing),
            "choose a new version or verify the existing tag before publishing",
        )
    return CheckResult("git tag", "git rev-parse --verify refs/tags/<version>", PASS, 0, "no current-version tag exists", "none")


def _check_existing_dist(root: Path, version: str) -> CheckResult:
    dist = root / "dist"
    artifacts = [path for path in dist.glob("*") if path.is_file()] if dist.exists() else []
    release_artifacts = [path for path in artifacts if path.suffix in {".whl", ".gz", ".zip"}]
    if not release_artifacts:
        return CheckResult("existing dist artifacts", "dist/", PASS, 0, "no existing release artifacts need freshness review", "none")
    wrong_version = [path.name for path in release_artifacts if f"-{version}" not in path.name]
    if wrong_version:
        return CheckResult(
            "existing dist artifacts",
            "dist/",
            FAIL,
            1,
            "dist contains artifacts for another version: " + ", ".join(sorted(wrong_version)),
            "move stale artifacts away before running publish readiness",
        )
    return CheckResult("existing dist artifacts", "dist/", PASS, 0, "existing artifacts match the current version", "fresh build still required")


def _check_fresh_artifacts(root: Path, version: str, build_started_at: float) -> CheckResult:
    dist = root / "dist"
    artifacts = sorted(path for path in dist.glob("*") if path.is_file()) if dist.exists() else []
    expected = [path for path in artifacts if f"-{version}" in path.name and path.suffix in {".whl", ".gz", ".zip"}]
    if not expected:
        return CheckResult(
            "fresh build artifacts",
            "dist/",
            FAIL,
            1,
            "build completed but no current-version artifacts were found",
            "inspect python -m build output and dist/",
        )
    stale = [path.name for path in expected if path.stat().st_mtime < build_started_at]
    if stale:
        return CheckResult(
            "fresh build artifacts",
            "dist/",
            FAIL,
            1,
            "current-version artifacts were not regenerated in this run: " + ", ".join(stale),
            "remove dist/ and rerun python -m build",
        )
    return CheckResult("fresh build artifacts", "dist/", PASS, 0, "current-version artifacts were regenerated in this run", "none")


def _run_command_check(
    root: Path,
    label: str,
    display: str,
    command: Sequence[str],
    *,
    runner: Runner,
    env: dict[str, str],
) -> CheckResult:
    completed = _run_raw(root, command, runner, env)
    leaked = _contains_secret(completed.stdout) or _contains_secret(completed.stderr)
    if leaked:
        return CheckResult(
            label,
            display,
            FAIL,
            completed.returncode,
            "command output contained a publish token or API key pattern; output suppressed",
            "rotate the secret and remove it from command output",
        )
    if completed.returncode == 0:
        if label == "golden benchmark eval":
            try:
                payload = json.loads(completed.stdout)
                if not isinstance(payload, dict) or not isinstance(payload.get("metrics"), dict):
                    raise ValueError("metrics missing")
            except (json.JSONDecodeError, ValueError):
                return CheckResult(
                    label,
                    display,
                    FAIL,
                    1,
                    "benchmark command returned non-metric JSON",
                    "run `antemortem eval benchmarks/golden_cases --json` and inspect output",
                )
        return CheckResult(label, display, PASS, 0, "command passed", "none")
    return CheckResult(
        label,
        display,
        _classify_failure(label, completed),
        completed.returncode,
        "command failed",
        f"run `{display}` and inspect the failure output",
    )


def _classify_failure(label: str, completed: subprocess.CompletedProcess[str]) -> str:
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    lowered = output.lower()
    if "network disabled" in lowered or "failed to fetch" in lowered:
        return NETWORK_BLOCKED
    if "failed to establish a new connection" in lowered or "winerror 10013" in lowered or "os error 10013" in lowered or "socket" in lowered:
        return ENVIRONMENT_BLOCKED
    if any(
        marker in lowered
        for marker in (
            "no module named build",
            "no module named twine",
            "no module named hatchling",
            "tooling_missing",
            "missing packaging verification tooling",
        )
    ):
        return TOOLING_MISSING
    if label in {"working tree", "git tag"}:
        return GIT_STATE_BLOCKED
    return FAIL


def _twine_command(root: Path) -> list[str]:
    artifacts = sorted(str(path) for path in (root / "dist").glob("*") if path.is_file())
    return [sys.executable, "-m", "twine", "check", *(artifacts or ["dist/*"])]


def _run_raw(
    root: Path,
    command: Sequence[str],
    runner: Runner,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return runner(
        list(command),
        cwd=root,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def _contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def _summary(
    checks: Sequence[CheckResult],
    failures: int,
    allow_dirty: bool,
    skip_git_checks: bool,
    continue_on_error: bool,
    version: str,
) -> tuple[int, dict[str, object]]:
    return (
        0 if failures == 0 else 1,
        {
            "ok": failures == 0,
            "version": version,
            "failed_count": failures,
            "allow_dirty": allow_dirty,
            "skip_git_checks": skip_git_checks,
            "continue_on_error": continue_on_error,
            "checks": [check.as_json() for check in checks],
        },
    )


def _load_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _readiness_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    src = str(root / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not existing else src + os.pathsep + existing
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="Print stable JSON.")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow a dirty working tree.")
    parser.add_argument("--skip-git-checks", action="store_true", help="Skip git worktree and tag checks.")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Run all checks and report every blocker.",
    )
    args = parser.parse_args(argv)

    exit_code, summary = run_publish_readiness(
        args.root,
        allow_dirty=args.allow_dirty,
        skip_git_checks=args.skip_git_checks,
        continue_on_error=args.continue_on_error,
    )
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        for check in summary["checks"]:
            print(
                f"{check['classification']}: {check['label']} - {check['message']}"
            )
            if check["classification"] != PASS:
                print(f"  Command: {check['command']}")
                print(f"  Next: {check['next']}")
        if exit_code == 0:
            print("\nPublish readiness gate passed. Manual publish remains a separate action.")
        else:
            print("\nPublish readiness gate failed.", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
