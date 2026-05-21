# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Generate deterministic release notes from repository evidence.

The generator does not infer product changes from filenames. Semantic release
content comes from CHANGELOG.md; git or explicit file input only contributes a
factual changed-file inventory. Benchmark metrics are rendered only from JSON
produced by the offline benchmark command or an explicit JSON file.
"""

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


BENCHMARK_COMMAND = "antemortem eval benchmarks/golden_cases --json"
CONSISTENCY_COMMAND = "python scripts/check_repo_consistency.py"
VERIFICATION_COMMANDS = (
    'python -m pip install -e ".[dev]"',
    "pytest -q",
    CONSISTENCY_COMMAND,
    "python scripts/generate_readme_claims.py --check",
    "python scripts/release_audit.py",
    BENCHMARK_COMMAND,
    "python -m build",
    "python -m twine check dist/*",
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class ChangedFile:
    status: str
    path: str


@dataclass(frozen=True)
class CommandResult:
    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def status(self) -> str:
        return "passed" if self.exit_code == 0 else "failed"


@dataclass(frozen=True)
class ChangelogSection:
    found: bool
    heading: str
    categories: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class BenchmarkSnapshot:
    metrics: dict[str, float]
    totals: dict[str, int]
    source: str
    command_result: CommandResult | None


@dataclass(frozen=True)
class ReleaseNotesData:
    version: str
    source_label: str
    changed_files: tuple[ChangedFile, ...]
    changelog: ChangelogSection
    benchmark: BenchmarkSnapshot
    consistency: CommandResult


def generate_release_notes(
    root: Path,
    *,
    version: str | None = None,
    from_ref: str | None = None,
    to_ref: str | None = None,
    explicit_files: Sequence[str] = (),
    benchmark_json: Path | None = None,
    runner: Runner = subprocess.run,
) -> str:
    """Collect release-note inputs and render markdown."""
    root = root.resolve()
    release_version = version or _load_pyproject_version(root)
    changed_files = collect_changed_files(
        root,
        from_ref=from_ref,
        to_ref=to_ref,
        explicit_files=explicit_files,
        runner=runner,
    )
    changelog = extract_changelog_section(root / "CHANGELOG.md", release_version)
    benchmark = load_benchmark_snapshot(root, benchmark_json=benchmark_json, runner=runner)
    consistency = run_consistency_checker(root, runner=runner)
    source_label = _source_label(from_ref, to_ref, explicit_files)

    data = ReleaseNotesData(
        version=release_version,
        source_label=source_label,
        changed_files=changed_files,
        changelog=changelog,
        benchmark=benchmark,
        consistency=consistency,
    )
    return render_release_notes(data)


def collect_changed_files(
    root: Path,
    *,
    from_ref: str | None = None,
    to_ref: str | None = None,
    explicit_files: Sequence[str] = (),
    runner: Runner = subprocess.run,
) -> tuple[ChangedFile, ...]:
    """Return changed files from explicit input or git diff/status."""
    if explicit_files:
        return tuple(sorted((_parse_explicit_file(item) for item in explicit_files), key=lambda item: item.path))

    git_commands = _git_change_commands(from_ref, to_ref)
    changed: list[ChangedFile] = []
    errors: list[str] = []
    env = _subprocess_env(root)
    for command in git_commands:
        result = runner(
            command,
            cwd=root,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append((result.stderr or result.stdout or "git command failed").strip())
            continue
        changed.extend(_parse_git_name_status(result.stdout))

    if errors and not changed:
        raise RuntimeError(
            "git metadata unavailable; pass --files with explicit changed paths. "
            + " | ".join(errors)
        )
    return tuple(sorted(_dedupe_changed_files(changed), key=lambda item: item.path))


def extract_changelog_section(path: Path, version: str) -> ChangelogSection:
    if not path.exists():
        return ChangelogSection(False, "", {})

    text = path.read_text(encoding="utf-8")
    block, heading = _find_changelog_block(text, version)
    if block is None:
        return ChangelogSection(False, "", {})

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
    return ChangelogSection(
        True,
        heading,
        {key: tuple(value) for key, value in sorted(categories.items())},
    )


def load_benchmark_snapshot(
    root: Path,
    *,
    benchmark_json: Path | None = None,
    runner: Runner = subprocess.run,
) -> BenchmarkSnapshot:
    if benchmark_json is not None:
        path = benchmark_json if benchmark_json.is_absolute() else root / benchmark_json
        data = _load_json_payload(path.read_text(encoding="utf-8"))
        return BenchmarkSnapshot(
            metrics=_metric_map(data),
            totals=_total_map(data),
            source=str(benchmark_json).replace("\\", "/"),
            command_result=None,
        )

    command = [sys.executable, "-m", "antemortem.cli", "eval", "benchmarks/golden_cases", "--json"]
    result = runner(
        command,
        cwd=root,
        env=_subprocess_env(root),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    command_result = CommandResult(
        command=BENCHMARK_COMMAND,
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"benchmark command failed with exit code {result.returncode}: "
            + (result.stderr or result.stdout)
        )
    data = _load_json_payload(result.stdout)
    return BenchmarkSnapshot(
        metrics=_metric_map(data),
        totals=_total_map(data),
        source=BENCHMARK_COMMAND,
        command_result=command_result,
    )


def run_consistency_checker(root: Path, *, runner: Runner = subprocess.run) -> CommandResult:
    result = runner(
        [sys.executable, "scripts/check_repo_consistency.py"],
        cwd=root,
        env=_subprocess_env(root),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return CommandResult(
        command=CONSISTENCY_COMMAND,
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def render_release_notes(data: ReleaseNotesData) -> str:
    added_files = _files_by_status(data.changed_files, {"A", "??"})
    changed_files = _files_by_status(data.changed_files, {"M", "R", "C", "explicit"})
    deleted_files = _files_by_status(data.changed_files, {"D"})
    changelog_added = _category_items(data.changelog, "Added")
    changelog_changed = _category_items(data.changelog, "Changed")
    changelog_fixed = _category_items(data.changelog, "Fixed")
    breaking = _breaking_items(data.changelog)
    limitations = _known_limitations(data, deleted_files)

    lines = [
        f"# Release Notes: antemortem {data.version}",
        "",
        "## Summary",
        "",
        f"- Package version: `{data.version}`",
        f"- Change source: {data.source_label}",
        f"- Changed files considered: `{len(data.changed_files)}`",
        f"- CHANGELOG source: {_changelog_summary(data.changelog, data.version)}",
        f"- Consistency checker: `{data.consistency.status}` (exit `{data.consistency.exit_code}`)",
        "",
        "## Added",
        "",
        *_render_items(changelog_added, "No Added entries declared in CHANGELOG.md for this version."),
        *_render_file_items(added_files, "File added"),
        "",
        "## Changed",
        "",
        *_render_items(changelog_changed, "No Changed entries declared in CHANGELOG.md for this version."),
        *_render_file_items(changed_files, "File changed"),
        "",
        "## Fixed",
        "",
        *_render_items(changelog_fixed, "No Fixed entries declared in CHANGELOG.md for this version."),
        "",
        "## Verification commands",
        "",
        *_verification_lines(data),
        "",
        "## Benchmark snapshot",
        "",
        f"- Provenance: {_benchmark_provenance(data.benchmark)}",
        f"- Source: `{data.benchmark.source}`",
        f"- Totals: {_render_totals(data.benchmark.totals)}",
        f"- Metrics: {_render_metrics(data.benchmark.metrics)}",
        "",
        "## Breaking changes",
        "",
        *_render_items(breaking, "No breaking changes declared in CHANGELOG.md for this version."),
        "",
        "## Known limitations",
        "",
        *_render_items(limitations, "No generator limitations recorded."),
        "",
    ]
    return "\n".join(lines)


def _benchmark_provenance(snapshot: BenchmarkSnapshot) -> str:
    if snapshot.command_result is None:
        return "Benchmark metrics read from generated JSON file"
    return "Benchmark metrics generated by offline benchmark command"


def _load_pyproject_version(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        raise RuntimeError(f"pyproject.toml not found under {root}")
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _git_change_commands(from_ref: str | None, to_ref: str | None) -> list[list[str]]:
    if from_ref and to_ref:
        return [["git", "diff", "--name-status", from_ref, to_ref]]
    if from_ref:
        return [["git", "diff", "--name-status", from_ref, "HEAD"]]
    if to_ref:
        return [["git", "diff", "--name-status", to_ref]]
    return [
        ["git", "diff", "--name-status", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]


def _parse_git_name_status(text: str) -> list[ChangedFile]:
    changed: list[ChangedFile] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 1:
            changed.append(ChangedFile("??", parts[0]))
            continue
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            changed.append(ChangedFile("R", f"{parts[1]} -> {parts[2]}"))
        else:
            changed.append(ChangedFile(status[:1], parts[-1]))
    return changed


def _parse_explicit_file(raw: str) -> ChangedFile:
    if ":" in raw:
        status, path = raw.split(":", 1)
        normalized_status = status.strip()
        if normalized_status in {"A", "M", "D", "R", "C", "??"}:
            return ChangedFile(normalized_status, path.strip())
    return ChangedFile("explicit", raw.strip())


def _dedupe_changed_files(files: Sequence[ChangedFile]) -> tuple[ChangedFile, ...]:
    by_path: dict[str, ChangedFile] = {}
    for item in files:
        by_path[item.path] = item
    return tuple(by_path.values())


def _find_changelog_block(text: str, version: str) -> tuple[str | None, str]:
    headings = list(re.finditer(r"^##\s+(?P<title>.+?)\s*$", text, flags=re.M))
    wanted = {version, f"v{version}"}
    if version.lower() == "unreleased":
        wanted.add("Unreleased")
    for index, match in enumerate(headings):
        title = match.group("title").strip()
        normalized = title.split(" - ", 1)[0].strip().strip("[]")
        if normalized in wanted:
            start = match.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            return text[start:end].strip(), title
    return None, ""


def _load_json_payload(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("benchmark JSON could not be parsed") from exc
    if not isinstance(data, dict):
        raise RuntimeError("benchmark JSON root must be an object")
    if "metrics" not in data or not isinstance(data["metrics"], dict):
        raise RuntimeError("benchmark JSON is missing a metrics object")
    return data


def _metric_map(data: dict[str, Any]) -> dict[str, float]:
    metrics = data.get("metrics", {})
    if not metrics:
        raise RuntimeError("benchmark metrics object is empty")
    return {str(key): float(value) for key, value in sorted(metrics.items())}


def _total_map(data: dict[str, Any]) -> dict[str, int]:
    totals = data.get("totals", {})
    if not isinstance(totals, dict):
        return {}
    return {str(key): int(value) for key, value in sorted(totals.items())}


def _files_by_status(files: Sequence[ChangedFile], statuses: set[str]) -> tuple[ChangedFile, ...]:
    return tuple(item for item in files if item.status in statuses)


def _category_items(changelog: ChangelogSection, category: str) -> tuple[str, ...]:
    return changelog.categories.get(category, ())


def _breaking_items(changelog: ChangelogSection) -> tuple[str, ...]:
    items: list[str] = []
    for category in ("Breaking", "Breaking changes", "Removed"):
        items.extend(changelog.categories.get(category, ()))
    return tuple(items)


def _render_items(items: Sequence[str], empty_message: str) -> list[str]:
    if items:
        return list(items)
    return [f"- {empty_message}"]


def _render_file_items(items: Sequence[ChangedFile], label: str) -> list[str]:
    return [f"- {label}: `{item.path}`" for item in items]


def _verification_lines(data: ReleaseNotesData) -> list[str]:
    lines: list[str] = []
    for command in VERIFICATION_COMMANDS:
        if command == BENCHMARK_COMMAND:
            if data.benchmark.command_result is not None:
                result = data.benchmark.command_result
                lines.append(f"- `{result.command}` -> {result.status} (exit `{result.exit_code}`)")
            else:
                lines.append(
                    f"- `{command}` -> metrics read from generated JSON file `{data.benchmark.source}`"
                )
            continue
        if command == data.consistency.command:
            result = data.consistency
            lines.append(f"- `{result.command}` -> {result.status} (exit `{result.exit_code}`)")
            continue
        lines.append(f"- `{command}`")
    return lines


def _render_totals(totals: dict[str, int]) -> str:
    if not totals:
        return "`none`"
    return ", ".join(f"`{key}={value}`" for key, value in totals.items())


def _render_metrics(metrics: dict[str, float]) -> str:
    return ", ".join(f"`{key}={value:.3f}`" for key, value in metrics.items())


def _changelog_summary(changelog: ChangelogSection, version: str) -> str:
    if changelog.found:
        return f"`CHANGELOG.md` section `{changelog.heading}`"
    return f"`CHANGELOG.md` has no section for `{version}`"


def _known_limitations(data: ReleaseNotesData, deleted_files: Sequence[ChangedFile]) -> list[str]:
    limitations: list[str] = []
    if data.source_label == "explicit file input":
        limitations.append("- Generated from explicit file input because git metadata was not required.")
    if not data.changelog.found:
        limitations.append(f"- No CHANGELOG.md section found for `{data.version}`; semantic changes are not inferred.")
    if data.consistency.exit_code != 0:
        limitations.append(f"- Consistency checker failed with exit `{data.consistency.exit_code}`.")
    for item in deleted_files:
        limitations.append(f"- Deleted file detected: `{item.path}`. Review manually for migration notes.")
    return limitations


def _source_label(from_ref: str | None, to_ref: str | None, explicit_files: Sequence[str]) -> str:
    if explicit_files:
        return "explicit file input"
    if from_ref and to_ref:
        return f"`git diff --name-status {from_ref} {to_ref}`"
    if from_ref:
        return f"`git diff --name-status {from_ref} HEAD`"
    if to_ref:
        return f"`git diff --name-status {to_ref}`"
    return "`git diff --name-status HEAD` plus untracked files"


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
    parser.add_argument("--from", dest="from_ref", help="Start git ref for the release diff.")
    parser.add_argument("--to", dest="to_ref", help="End git ref for the release diff.")
    parser.add_argument("--output", type=Path, help="Write release notes to this markdown file.")
    parser.add_argument(
        "--files",
        nargs="+",
        default=(),
        help="Explicit changed files when git metadata is unavailable. Optional status form: A:path.",
    )
    parser.add_argument(
        "--benchmark-json",
        type=Path,
        help="Read benchmark metrics from generated JSON instead of running the benchmark command.",
    )
    args = parser.parse_args(argv)

    try:
        notes = generate_release_notes(
            args.root,
            version=args.release_version,
            from_ref=args.from_ref,
            to_ref=args.to_ref,
            explicit_files=args.files,
            benchmark_json=args.benchmark_json,
            runner=subprocess.run,
        )
    except Exception as exc:  # pragma: no cover - exercised through CLI behavior
        print(f"FAIL: release notes generation failed: {exc}", file=sys.stderr)
        return 1

    if args.output:
        output = args.output if args.output.is_absolute() else args.root / args.output
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(notes, encoding="utf-8", newline="\n")
        except OSError as exc:
            print(f"FAIL: could not write release notes to {output}: {exc}", file=sys.stderr)
            return 1
    else:
        print(notes, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
