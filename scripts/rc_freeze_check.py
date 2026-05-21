# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Check whether the repository is safe to freeze as a release candidate."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence


README_FILES = (
    "README.md",
    "README_KR.md",
    "EASY_README.md",
    "EASY_README_KR.md",
)
GENERATED_CLAIM_REFS = ("docs/generated/claims.md", "docs/generated/claims_kr.md")
PUBLIC_TODO_RE = re.compile(r"\b(TODO|FIXME)\b", re.I)
DEV_VERSION_RE = re.compile(r"(?:^0\.0\.0|dev|dirty|snapshot|placeholder|\+)", re.I)

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class CheckResult:
    label: str
    status: str
    command: str
    exit_code: int | None
    message: str
    next_step: str

    def as_json(self) -> dict[str, object]:
        return {
            "label": self.label,
            "status": self.status,
            "command": self.command,
            "exit_code": self.exit_code,
            "message": self.message,
            "next": self.next_step,
        }


@dataclass(frozen=True)
class AuditCoverage:
    parent: bool
    exit_code: int
    steps: dict[str, str]
    raw_output: str

    def passed(self, command: str) -> bool:
        if self.parent:
            return command in REQUIRED_AUDIT_COMMANDS
        return self.steps.get(command) == "passed"


REQUIRED_AUDIT_COMMANDS = {
    "pytest -q",
    "python scripts/check_repo_consistency.py",
    "python scripts/generate_readme_claims.py --check",
    "python scripts/check_claim_ledger.py",
    "antemortem eval benchmarks/golden_cases --json",
}


def run_freeze_check(
    root: Path,
    *,
    continue_on_error: bool = False,
    allow_dirty: bool = False,
    runner: Runner = subprocess.run,
    env: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    root = root.resolve()
    env = _check_env(root, env)
    results: list[CheckResult] = []
    failures = 0

    def record(result: CheckResult) -> bool:
        nonlocal failures
        results.append(result)
        if result.status == "failed":
            failures += 1
            return continue_on_error
        return True

    audit = _collect_release_audit_coverage(root, runner=runner, env=env, continue_on_error=True)
    if not record(_release_audit_result(audit)):
        return _summary(results, failures, continue_on_error, allow_dirty)

    for result in (
        _check_worktree(root, allow_dirty=allow_dirty, runner=runner, env=env),
        _check_pyproject_version(root),
        _check_changelog_entry(root),
        _check_readme_generated_claim_refs(root),
        _check_public_todos(root),
        _check_dist_freshness(root),
    ):
        if not record(result):
            return _summary(results, failures, continue_on_error, allow_dirty)

    command_checks = (
        ("pytest", "pytest -q", [sys.executable, "-m", "pytest", "-q"]),
        (
            "repository consistency",
            "python scripts/check_repo_consistency.py",
            [sys.executable, "scripts/check_repo_consistency.py"],
        ),
        (
            "generated README claims",
            "python scripts/generate_readme_claims.py --check",
            [sys.executable, "scripts/generate_readme_claims.py", "--check"],
        ),
        (
            "public claim ledger",
            "python scripts/check_claim_ledger.py",
            [sys.executable, "scripts/check_claim_ledger.py"],
        ),
        (
            "offline benchmark JSON",
            "antemortem eval benchmarks/golden_cases --json",
            ["antemortem", "eval", "benchmarks/golden_cases", "--json"],
        ),
    )
    for label, display, command in command_checks:
        if audit.passed(display):
            result = CheckResult(
                label=label,
                status="passed",
                command=display,
                exit_code=0,
                message="covered by release_audit.py output",
                next_step="none",
            )
        else:
            result = _run_command_check(root, label, display, command, runner=runner, env=env)
        if not record(result):
            return _summary(results, failures, continue_on_error, allow_dirty)

    return _summary(results, failures, continue_on_error, allow_dirty)


def _collect_release_audit_coverage(
    root: Path,
    *,
    runner: Runner,
    env: dict[str, str],
    continue_on_error: bool,
) -> AuditCoverage:
    if env.get("ANTEMORTEM_RELEASE_AUDIT_PARENT") == "1":
        return AuditCoverage(True, 0, {command: "passed" for command in REQUIRED_AUDIT_COMMANDS}, "")

    script = root / "scripts" / "release_audit.py"
    if not script.exists():
        return AuditCoverage(False, 1, {}, "scripts/release_audit.py is missing")

    command = [sys.executable, "scripts/release_audit.py", "--json"]
    if continue_on_error:
        command.insert(-1, "--continue-on-error")
    completed = runner(
        command,
        cwd=root,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    steps: dict[str, str] = {}
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        payload = {}
    for step in payload.get("steps", []):
        if isinstance(step, dict) and "command" in step and "status" in step:
            steps[str(step["command"])] = str(step["status"])
    return AuditCoverage(False, completed.returncode, steps, completed.stdout + completed.stderr)


def _release_audit_result(audit: AuditCoverage) -> CheckResult:
    if audit.parent:
        return CheckResult(
            "release audit",
            "passed",
            "python scripts/release_audit.py",
            0,
            "running under release_audit.py parent command",
            "none",
        )
    if audit.exit_code == 0:
        return CheckResult(
            "release audit",
            "passed",
            "python scripts/release_audit.py --json",
            0,
            "release audit completed successfully",
            "none",
        )
    return CheckResult(
        "release audit",
        "failed",
        "python scripts/release_audit.py --json",
        audit.exit_code,
        "release audit did not complete successfully",
        "run python scripts/release_audit.py --continue-on-error for the full failure inventory",
    )


def _check_worktree(root: Path, *, allow_dirty: bool, runner: Runner, env: dict[str, str]) -> CheckResult:
    if allow_dirty:
        return CheckResult(
            "worktree state",
            "passed",
            "git status --porcelain",
            0,
            "dirty worktree allowed for local development",
            "omit --allow-dirty before freezing the RC",
        )
    completed = runner(
        ["git", "-c", f"safe.directory={root.as_posix()}", "status", "--porcelain"],
        cwd=root,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return CheckResult(
            "worktree state",
            "failed",
            "git status --porcelain",
            completed.returncode,
            "git status could not be read",
            "fix git safe.directory/permissions or rerun with --allow-dirty for local development",
        )
    if completed.stdout.strip():
        return CheckResult(
            "worktree state",
            "failed",
            "git status --porcelain",
            1,
            "uncommitted changes are present",
            "commit/stash changes, or use --allow-dirty only for local development",
        )
    return CheckResult("worktree state", "passed", "git status --porcelain", 0, "worktree is clean", "none")


def _check_pyproject_version(root: Path) -> CheckResult:
    version = _load_version(root)
    if DEV_VERSION_RE.search(version):
        return CheckResult(
            "pyproject version",
            "failed",
            "pyproject.toml",
            1,
            f"version `{version}` looks like a dev placeholder",
            "set project.version to the exact RC candidate version",
        )
    return CheckResult("pyproject version", "passed", "pyproject.toml", 0, f"version `{version}` is release-shaped", "none")


def _check_changelog_entry(root: Path) -> CheckResult:
    version = _load_version(root)
    path = root / "CHANGELOG.md"
    if not path.exists():
        return CheckResult("CHANGELOG entry", "failed", "CHANGELOG.md", 1, "CHANGELOG.md is missing", "add a CHANGELOG.md entry for the current version")
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^##\s+\[?v?{re.escape(version)}\]?(?:\s+-\s+.*)?$", re.M)
    if not pattern.search(text):
        return CheckResult(
            "CHANGELOG entry",
            "failed",
            "CHANGELOG.md",
            1,
            f"no entry found for version `{version}`",
            f"add `## [{version}] - YYYY-MM-DD` before freezing",
        )
    return CheckResult("CHANGELOG entry", "passed", "CHANGELOG.md", 0, f"entry exists for `{version}`", "none")


def _check_readme_generated_claim_refs(root: Path) -> CheckResult:
    missing: list[str] = []
    for rel in README_FILES:
        path = root / rel
        if not path.exists():
            missing.append(f"{rel}: missing file")
            continue
        text = path.read_text(encoding="utf-8")
        for ref in GENERATED_CLAIM_REFS:
            if ref not in text:
                missing.append(f"{rel}: missing {ref}")
    if missing:
        return CheckResult(
            "README generated claims",
            "failed",
            "README files",
            1,
            "; ".join(missing),
            "add links to docs/generated/claims.md and docs/generated/claims_kr.md",
        )
    return CheckResult("README generated claims", "passed", "README files", 0, "all README variants reference generated claim blocks", "none")


def _check_public_todos(root: Path) -> CheckResult:
    allowlist = _load_todo_allowlist(root)
    hits: list[str] = []
    for rel in README_FILES:
        path = root / rel
        if not path.exists():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not PUBLIC_TODO_RE.search(line):
                continue
            if _todo_allowed(rel, line, allowlist):
                continue
            hits.append(f"{rel}:{line_no}: {line.strip()}")
    if hits:
        return CheckResult(
            "public TODO/FIXME",
            "failed",
            "README files",
            1,
            "; ".join(hits),
            "remove TODO/FIXME from public README sections or allowlist it with scripts/rc_freeze_allowlist.toml",
        )
    return CheckResult("public TODO/FIXME", "passed", "README files", 0, "no unallowlisted TODO/FIXME markers in README variants", "none")


def _check_dist_freshness(root: Path) -> CheckResult:
    dist = root / "dist"
    if not dist.exists() or not any(dist.iterdir()):
        return CheckResult("dist artifacts", "passed", "dist/", 0, "dist artifacts are absent", "none")
    artifacts = [path for path in dist.iterdir() if path.is_file()]
    source_mtime = _newest_source_mtime(root)
    stale = [path.name for path in artifacts if path.stat().st_mtime < source_mtime]
    if stale:
        return CheckResult(
            "dist artifacts",
            "failed",
            "dist/",
            1,
            "dist artifacts are older than source files: " + ", ".join(sorted(stale)),
            "remove dist/ or regenerate with python -m build immediately before freezing",
        )
    return CheckResult("dist artifacts", "passed", "dist/", 0, "dist artifacts are present and newer than checked source files", "none")


def _run_command_check(
    root: Path,
    label: str,
    display: str,
    command: Sequence[str],
    *,
    runner: Runner,
    env: dict[str, str],
) -> CheckResult:
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
    if completed.returncode == 0:
        if display == "antemortem eval benchmarks/golden_cases --json":
            try:
                payload = json.loads(completed.stdout)
                if not isinstance(payload.get("metrics"), dict):
                    raise ValueError("metrics missing")
            except (json.JSONDecodeError, ValueError):
                return CheckResult(
                    label,
                    "failed",
                    display,
                    1,
                    "benchmark command returned non-metric JSON",
                    "run antemortem eval benchmarks/golden_cases --json and inspect output",
                )
        return CheckResult(label, "passed", display, 0, "command passed", "none")
    return CheckResult(
        label,
        "failed",
        display,
        completed.returncode,
        "command failed",
        f"run `{display}` and inspect the failure output",
    )


def _summary(
    results: Sequence[CheckResult],
    failures: int,
    continue_on_error: bool,
    allow_dirty: bool,
) -> tuple[int, dict[str, object]]:
    return (
        0 if failures == 0 else 1,
        {
            "ok": failures == 0,
            "failed_count": failures,
            "continue_on_error": continue_on_error,
            "allow_dirty": allow_dirty,
            "checks": [result.as_json() for result in results],
        },
    )


def _load_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _newest_source_mtime(root: Path) -> float:
    roots = [
        root / "pyproject.toml",
        root / "CHANGELOG.md",
        *(root / rel for rel in README_FILES),
        root / "src",
        root / "scripts",
        root / "docs",
    ]
    newest = 0.0
    for path in roots:
        if not path.exists():
            continue
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
            continue
        for child in path.rglob("*"):
            if child.is_file() and "__pycache__" not in child.parts:
                newest = max(newest, child.stat().st_mtime)
    return newest


def _load_todo_allowlist(root: Path) -> tuple[tuple[str | None, str], ...]:
    path = root / "scripts" / "rc_freeze_allowlist.toml"
    if not path.exists():
        return ()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    entries: list[tuple[str | None, str]] = []
    for item in data.get("allow", []):
        entries.append((item.get("path"), item["contains"]))
    return tuple(entries)


def _todo_allowed(path: str, line: str, allowlist: Iterable[tuple[str | None, str]]) -> bool:
    for allowed_path, contains in allowlist:
        if allowed_path and allowed_path.replace("\\", "/") != path.replace("\\", "/"):
            continue
        if contains in line:
            return True
    return False


def _check_env(root: Path, env: dict[str, str] | None) -> dict[str, str]:
    merged = dict(os.environ if env is None else env)
    merged.setdefault("PYTHONUTF8", "1")
    src = str(root / "src")
    existing = merged.get("PYTHONPATH")
    merged["PYTHONPATH"] = src if not existing else src + os.pathsep + existing
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="Print a stable JSON result.")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Run all checks and report every failure instead of stopping at the first.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow a dirty worktree for local development only.",
    )
    args = parser.parse_args(argv)

    exit_code, summary = run_freeze_check(
        args.root,
        continue_on_error=args.continue_on_error,
        allow_dirty=args.allow_dirty,
    )
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        for check in summary["checks"]:
            prefix = "PASS" if check["status"] == "passed" else "FAIL"
            print(f"{prefix}: {check['label']} — {check['message']}")
            if check["status"] == "failed":
                print(f"  Command: {check['command']}")
                print(f"  Next: {check['next']}")
        if exit_code == 0:
            print("\nRC freeze check passed.")
        else:
            print("\nRC freeze check failed.", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
