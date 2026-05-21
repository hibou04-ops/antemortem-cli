# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Generate a factual GitHub Release draft without publishing it."""

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
from typing import Any, Callable, Sequence


Runner = Callable[..., subprocess.CompletedProcess[str]]

BENCHMARK_COMMAND = "antemortem eval benchmarks/golden_cases --json"
STATUS_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pytest", (sys.executable, "-m", "pytest", "-q")),
    ("consistency checker", (sys.executable, "scripts/check_repo_consistency.py")),
    (
        "generated claims check",
        (sys.executable, "scripts/generate_readme_claims.py", "--check"),
    ),
    ("golden benchmark eval", ("antemortem", "eval", "benchmarks/golden_cases", "--json")),
    ("package build", (sys.executable, "-m", "build")),
    ("twine check", (sys.executable, "-m", "twine", "check", "dist/*")),
    ("wheel smoke install", (sys.executable, "scripts/smoke_wheel_install.py")),
    ("release audit", (sys.executable, "scripts/release_audit.py", "--json")),
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    command: str
    exit_code: int
    status: str
    classification: str
    stdout: str = ""
    stderr: str = ""

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class ChangelogSection:
    heading: str
    categories: dict[str, tuple[str, ...]]


def generate_github_release_draft(
    root: Path,
    *,
    version: str | None = None,
    benchmark_json: Path | None = None,
    runner: Runner = subprocess.run,
) -> str:
    root = root.resolve()
    release_version = version or _load_pyproject_version(root)
    changelog = _extract_changelog(root / "CHANGELOG.md", release_version)
    results = _run_status_checks(root, benchmark_json=benchmark_json, runner=runner)
    benchmark = _benchmark_snapshot(results, benchmark_json=benchmark_json, root=root)
    return _render_draft(release_version, changelog, results, benchmark)


def _run_status_checks(
    root: Path,
    *,
    benchmark_json: Path | None,
    runner: Runner,
) -> tuple[CheckResult, ...]:
    results: list[CheckResult] = []
    for name, command in STATUS_COMMANDS:
        if name == "golden benchmark eval" and benchmark_json is not None:
            data_path = benchmark_json if benchmark_json.is_absolute() else root / benchmark_json
            stdout = data_path.read_text(encoding="utf-8")
            results.append(
                CheckResult(
                    name=name,
                    command=f"{BENCHMARK_COMMAND} (from {benchmark_json})",
                    exit_code=0,
                    status="passed",
                    classification="PASSED",
                    stdout=stdout,
                )
            )
            continue
        resolved = _resolve_command(root, command)
        completed = _run_command(root, resolved, runner)
        results.append(
            CheckResult(
                name=name,
                command=_display_command(name),
                exit_code=completed.returncode,
                status="passed" if completed.returncode == 0 else "failed",
                classification=_classify_result(name, completed),
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        )
    return tuple(results)


def _run_command(
    root: Path,
    command: Sequence[str],
    runner: Runner,
) -> subprocess.CompletedProcess[str]:
    return runner(
        list(command),
        cwd=root,
        env=_subprocess_env(root),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def _resolve_command(root: Path, command: Sequence[str]) -> tuple[str, ...]:
    if tuple(command[:4]) == (sys.executable, "-m", "twine", "check"):
        artifacts = sorted(str(path) for path in (root / "dist").glob("*") if path.is_file())
        return (sys.executable, "-m", "twine", "check", *(artifacts or ["dist/*"]))
    return tuple(command)


def _display_command(name: str) -> str:
    mapping = {
        "pytest": "pytest -q",
        "consistency checker": "python scripts/check_repo_consistency.py",
        "generated claims check": "python scripts/generate_readme_claims.py --check",
        "golden benchmark eval": BENCHMARK_COMMAND,
        "package build": "python -m build",
        "twine check": "python -m twine check dist/*",
        "wheel smoke install": "python scripts/smoke_wheel_install.py",
        "release audit": "python scripts/release_audit.py --json",
    }
    return mapping[name]


def _classify_result(name: str, completed: subprocess.CompletedProcess[str]) -> str:
    if completed.returncode == 0:
        return "PASSED"
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    release_audit_classification = _release_audit_classification(output)
    if release_audit_classification:
        return release_audit_classification
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
    if name in {"package build", "twine check", "wheel smoke install", "release audit"}:
        return "PACKAGING_FAILED"
    return "FAILED"


def _release_audit_classification(output: str) -> str:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return ""
    for step in steps:
        if isinstance(step, dict) and step.get("status") != "passed":
            classification = step.get("classification")
            return str(classification) if classification else ""
    return ""


def _benchmark_snapshot(
    results: Sequence[CheckResult],
    *,
    benchmark_json: Path | None,
    root: Path,
) -> dict[str, Any]:
    benchmark_result = next(item for item in results if item.name == "golden benchmark eval")
    if not benchmark_result.passed:
        return {
            "source": BENCHMARK_COMMAND,
            "error": "benchmark command did not pass; no metrics rendered",
        }
    try:
        data = json.loads(benchmark_result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("benchmark JSON could not be parsed") from exc
    if not isinstance(data, dict) or not isinstance(data.get("metrics"), dict):
        raise RuntimeError("benchmark JSON is missing a metrics object")
    source = str(benchmark_json).replace("\\", "/") if benchmark_json else BENCHMARK_COMMAND
    return {
        "source": source,
        "metrics": {str(key): float(value) for key, value in sorted(data["metrics"].items())},
        "totals": {
            str(key): int(value)
            for key, value in sorted(data.get("totals", {}).items())
            if isinstance(value, int)
        },
    }


def _render_draft(
    version: str,
    changelog: ChangelogSection,
    results: Sequence[CheckResult],
    benchmark: dict[str, Any],
) -> str:
    package_checks = {"package build", "twine check", "wheel smoke install"}
    package_ready = all(item.passed for item in results if item.name in package_checks)
    release_audit = next(item for item in results if item.name == "release audit")
    release_ready = package_ready and release_audit.passed
    lines = [
        f"# antemortem {version}",
        "",
        "## Summary",
        "",
        _summary_line(version, release_ready),
        "",
        "## Install",
        "",
        "After publication:",
        "",
        "```bash",
        f"pip install antemortem=={version}",
        "```",
        "",
        "## Quick Smoke Test",
        "",
        "From a clean checkout after installing the package:",
        "",
        "```bash",
        "antemortem --version",
        "antemortem --help",
        "antemortem doctor examples/demo_recon.md --repo . --json",
        "antemortem eval benchmarks/golden_cases --json",
        "```",
        "",
        "## Added",
        "",
        *_category_lines(changelog, "Added"),
        "",
        "## Changed",
        "",
        *_category_lines(changelog, "Changed"),
        "",
        "## Fixed",
        "",
        *_category_lines(changelog, "Fixed"),
        "",
        "## Verification Commands",
        "",
        "- `pytest -q`",
        "- `python scripts/check_repo_consistency.py`",
        "- `python scripts/generate_readme_claims.py --check`",
        f"- `{BENCHMARK_COMMAND}`",
        "- `python -m build`",
        "- `python -m twine check dist/*`",
        "- `python scripts/smoke_wheel_install.py`",
        "- `python scripts/release_audit.py --json`",
        "",
        "## Verification Status",
        "",
        "| Check | Command | Status | Classification | Exit |",
        "| --- | --- | --- | --- | --- |",
        *_status_lines(results),
        "",
        "## Benchmark Snapshot",
        "",
        *_benchmark_lines(benchmark),
        "",
        "## Known Limitations",
        "",
        *_limitation_lines(results, release_ready),
        "",
        "## Links",
        "",
        "- [README](../README.md)",
        "- [CHANGELOG](../CHANGELOG.md)",
        "- [Trust model](trust_model.md)",
        "- [Release hygiene](release_hygiene.md)",
        "- [Benchmark-backed claims](../README.md#benchmark-backed-claims)",
        "",
    ]
    return "\n".join(lines)


def _summary_line(version: str, release_ready: bool) -> str:
    if release_ready:
        return (
            f"Draft release notes for `antemortem` `{version}`. Local package build, "
            "metadata check, wheel smoke install, and release audit passed in this run."
        )
    return (
        f"Draft release notes for `antemortem` `{version}`. This draft is not publish-ready "
        "until package build, `twine check`, wheel smoke install, and release audit pass."
    )


def _category_lines(changelog: ChangelogSection, category: str) -> list[str]:
    items = changelog.categories.get(category, ())
    if not items:
        return [f"- No {category} entries declared in CHANGELOG.md for this version."]
    return list(items)


def _status_lines(results: Sequence[CheckResult]) -> list[str]:
    return [
        (
            f"| {item.name} | `{item.command}` | {item.status} | "
            f"`{item.classification}` | `{item.exit_code}` |"
        )
        for item in results
    ]


def _benchmark_lines(benchmark: dict[str, Any]) -> list[str]:
    if "error" in benchmark:
        return [f"- Source: `{benchmark['source']}`", f"- {benchmark['error']}"]
    metrics = benchmark.get("metrics", {})
    totals = benchmark.get("totals", {})
    metric_text = ", ".join(f"`{key}={value:.3f}`" for key, value in metrics.items())
    total_text = ", ".join(f"`{key}={value}`" for key, value in totals.items()) or "`none`"
    return [
        f"- Source: `{benchmark['source']}`",
        "- Provenance: generated machine-readable benchmark JSON.",
        f"- Totals: {total_text}",
        f"- Metrics: {metric_text}",
    ]


def _limitation_lines(results: Sequence[CheckResult], release_ready: bool) -> list[str]:
    limitations: list[str] = []
    if not release_ready:
        limitations.append(
            "- Packaging verification is incomplete. Do not publish until package build, "
            "`twine check`, wheel smoke install, and release audit pass."
        )
    for item in results:
        if item.passed:
            continue
        if item.classification in {"ENVIRONMENT_BLOCKED", "TOOLING_MISSING"}:
            limitations.append(
                f"- `{item.command}` did not pass: `{item.classification}`. "
                "Run the documented release verification path in a network-enabled environment."
            )
        else:
            limitations.append(
                f"- `{item.command}` did not pass: `{item.classification}` "
                f"(exit `{item.exit_code}`)."
            )
    if not limitations:
        return ["- No limitations recorded by the draft generator."]
    return limitations


def _extract_changelog(path: Path, version: str) -> ChangelogSection:
    if not path.exists():
        return ChangelogSection("", {})
    text = path.read_text(encoding="utf-8")
    block, heading = _find_changelog_block(text, version)
    if block is None:
        return ChangelogSection("", {})
    categories: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if line.startswith("### "):
            current = line[4:].strip()
            categories.setdefault(current, [])
            continue
        if current and line.startswith("- "):
            categories[current].append(line)
    return ChangelogSection(heading, {key: tuple(value) for key, value in categories.items()})


def _find_changelog_block(text: str, version: str) -> tuple[str | None, str]:
    headings = list(re.finditer(r"^##\s+(?P<title>.+?)\s*$", text, flags=re.M))
    wanted = {version, f"v{version}"}
    for index, match in enumerate(headings):
        title = match.group("title").strip()
        normalized = title.split(" - ", 1)[0].strip().strip("[]")
        if normalized in wanted:
            start = match.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            return text[start:end].strip(), title
    return None, ""


def _load_pyproject_version(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _subprocess_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    src = str(root / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not existing else src + os.pathsep + existing
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--version", dest="release_version", help="Release version to render.")
    parser.add_argument(
        "--benchmark-json",
        type=Path,
        help="Read benchmark metrics from generated JSON instead of running the benchmark command.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/github_release_draft.md"),
        help="Markdown output path.",
    )
    args = parser.parse_args(argv)

    try:
        draft = generate_github_release_draft(
            args.root,
            version=args.release_version,
            benchmark_json=args.benchmark_json,
            runner=subprocess.run,
        )
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"FAIL: GitHub release draft generation failed: {exc}", file=sys.stderr)
        return 1

    output = args.output if args.output.is_absolute() else args.root / args.output
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(draft, encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"FAIL: could not write release draft to {output}: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote GitHub release draft to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
