# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Check README claims against repository source of truth.

This script is intentionally offline and deterministic. It imports the CLI
only to read Typer's registered command names. It rejects exact public test
count claims because pytest collection can differ across OS and Python matrix
entries.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote


README_FILES = (
    "README.md",
    "README_KR.md",
    "EASY_README.md",
    "EASY_README_KR.md",
)

PROOF_ARTIFACT_FILES = (
    "examples/demo_recon.py",
    "examples/_demo_output.txt",
    "docs/demo/antemortem-cli-demo.en.srt",
)

OBSOLETE_DECISION_LABELS = frozenset(
    {
        "PROCEED",
        "REVISE_SPEC",
        "BLOCK",
        "SAFE",
    }
)

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
}

COMMAND_COUNT_PATTERNS = (
    re.compile(r"\b(?P<num>\d+|one|two|three|four|five|six|seven)[-\s]+command(?:s|\b)", re.I),
    re.compile(r"\b(?P<num>\d+|one|two|three|four|five|six|seven)\s+commands\b", re.I),
)

PROJECT_VERSION_RE = re.compile(r"(?<![\w.])(?:v0\.\d+(?:\.\d+)?|0\.\d+\.\d+)(?![\w.])")
PYPI_BADGE_RE = re.compile(r"img\.shields\.io/badge/pypi-([^-/]+)-", re.I)
TEST_BADGE_RE = re.compile(r"img\.shields\.io/badge/tests-(\d+)(?:%20|-)?passing-", re.I)
PROVIDER_BADGE_RE = re.compile(r"img\.shields\.io/badge/providers-([^)]*?)-informational\.svg", re.I)
PROVIDER_MATRIX_START = "<!-- provider-matrix:start -->"
PROVIDER_MATRIX_END = "<!-- provider-matrix:end -->"
TOTAL_TEST_CLAIM_RE = re.compile(
    r"(?<![\w.])(?P<count>\d{2,5})\s+tests?(?:,\s+|\s+passing|\s+and\s+CI|\s*[-·])",
    re.I,
)
BARE_ANTEMORTEM_COMMAND_RE = re.compile(r"^antemortem\s+([a-z][a-z0-9_-]*)\b")
BACKTICK_ANTEMORTEM_COMMAND_RE = re.compile(r"`antemortem\s+([a-z][a-z0-9_-]*)`")
BACKTICK_WORD_RE = re.compile(r"`([a-z][a-z0-9_-]*)`")
UPPER_LABEL_RE = re.compile(r"(?<![A-Z_])([A-Z][A-Z_]{2,})(?![A-Z_])")


@dataclass(frozen=True)
class RepositoryFacts:
    package_name: str
    package_version: str
    cli_commands: tuple[str, ...]
    decision_labels: tuple[str, ...]
    providers: tuple[str, ...]
    test_count: int


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    line: int
    message: str
    snippet: str

    def format(self) -> str:
        location = f"{self.path}:{self.line}" if self.line else self.path
        return f"{location}: [{self.code}] {self.message}\n    {self.snippet}"


@dataclass(frozen=True)
class AllowEntry:
    code: str | None
    path: str | None
    contains: str
    reason: str

    def matches(self, issue: Issue) -> bool:
        if self.code and self.code != issue.code:
            return False
        if self.path and self.path.replace("\\", "/") != issue.path.replace("\\", "/"):
            return False
        return self.contains in issue.snippet


def load_allowlist(path: Path) -> tuple[AllowEntry, ...]:
    if not path.exists():
        return ()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    entries = []
    for item in data.get("allow", []):
        entries.append(
            AllowEntry(
                code=item.get("code"),
                path=item.get("path"),
                contains=item["contains"],
                reason=item.get("reason", ""),
            )
        )
    return tuple(entries)


def collect_repository_facts(root: Path, *, collect_tests: bool = True) -> RepositoryFacts:
    pyproject = _load_pyproject(root)
    package_name = pyproject["project"]["name"]
    package_version = pyproject["project"]["version"]
    return RepositoryFacts(
        package_name=package_name,
        package_version=package_version,
        cli_commands=tuple(sorted(_load_cli_commands(root))),
        decision_labels=tuple(_load_decision_labels(root)),
        providers=tuple(_load_supported_providers(root)),
        test_count=0,
    )


def check_repository(
    root: Path,
    *,
    readme_files: Iterable[str] = README_FILES,
    proof_artifact_files: Iterable[str] = PROOF_ARTIFACT_FILES,
    allowlist_path: Path | None = None,
    facts: RepositoryFacts | None = None,
    check_generated_claims: bool | None = None,
    claim_facts: object | None = None,
) -> list[Issue]:
    root = root.resolve()
    readme_files = tuple(readme_files)
    facts = facts or collect_repository_facts(root)
    allowlist = load_allowlist(allowlist_path or root / "scripts" / "consistency_allowlist.toml")

    issues: list[Issue] = []
    for rel in readme_files:
        path = root / rel
        if not path.exists():
            issues.append(Issue("missing-readme", rel, 0, "expected README file is missing", rel))
            continue
        text = path.read_text(encoding="utf-8")
        issues.extend(_scan_readme(rel, text, facts))
    for rel in proof_artifact_files:
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        issues.extend(_scan_proof_artifact(rel, text, facts))
    if readme_files == README_FILES:
        issues.extend(_check_provider_compatibility_doc(root))
    if check_generated_claims is None:
        check_generated_claims = readme_files == README_FILES and (root / "pyproject.toml").exists()
    if check_generated_claims:
        issues.extend(_check_generated_claim_docs(root, claim_facts))
        issues.extend(_check_generated_claim_references(root, readme_files))

    return [issue for issue in issues if not any(entry.matches(issue) for entry in allowlist)]


def _scan_readme(path: str, text: str, facts: RepositoryFacts) -> list[Issue]:
    issues: list[Issue] = []
    command_set = set(facts.cli_commands)
    expected_command_count = len(command_set)
    expected_providers = set(facts.providers) | {"openai-compatible"}

    for line_no, line in enumerate(text.splitlines(), start=1):
        issues.extend(_check_versions(path, line_no, line, facts.package_version))
        issues.extend(_check_badges(path, line_no, line, facts, expected_providers))
        issues.extend(_check_command_counts(path, line_no, line, expected_command_count))
        issues.extend(_check_command_names(path, line_no, line, command_set))
        issues.extend(_check_command_lists(path, line_no, line, command_set))
        issues.extend(_check_decision_labels(path, line_no, line, set(facts.decision_labels)))
        issues.extend(_check_test_claims(path, line_no, line, facts.test_count))
        issues.extend(_check_package_name(path, line_no, line, facts.package_name))

    issues.extend(_check_provider_matrix(path, text, expected_providers))
    return issues


def _scan_proof_artifact(path: str, text: str, facts: RepositoryFacts) -> list[Issue]:
    issues: list[Issue] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        issues.extend(_check_test_claims(path, line_no, line, facts.test_count))
    return issues


def _check_versions(path: str, line_no: int, line: str, current_version: str) -> list[Issue]:
    issues: list[Issue] = []
    current = _version_tuple(current_version)
    for match in PROJECT_VERSION_RE.finditer(line):
        raw = match.group(0)
        version = raw[1:] if raw.startswith("v") else raw
        if _version_tuple(version) < current:
            issues.append(
                Issue(
                    "stale-version",
                    path,
                    line_no,
                    f"{raw} is older than package version {current_version}",
                    line.strip(),
                )
            )
    return issues


def _check_badges(
    path: str,
    line_no: int,
    line: str,
    facts: RepositoryFacts,
    expected_providers: set[str],
) -> list[Issue]:
    issues: list[Issue] = []
    if match := PYPI_BADGE_RE.search(line):
        badge_version = unquote(match.group(1))
        if badge_version != facts.package_version:
            issues.append(
                Issue(
                    "badge-version",
                    path,
                    line_no,
                    f"PyPI badge is {badge_version}, expected {facts.package_version}",
                    line.strip(),
                )
            )
    if match := TEST_BADGE_RE.search(line):
        issues.append(
            Issue(
                "test-count",
                path,
                line_no,
                "exact test-count badges are platform-dependent; use a nonnumeric CI verification badge",
                line.strip(),
            )
        )
    if match := PROVIDER_BADGE_RE.search(line):
        providers = _decode_provider_badge(match.group(1))
        if providers != expected_providers:
            issues.append(
                Issue(
                    "provider-badge",
                    path,
                    line_no,
                    f"provider badge is {sorted(providers)}, expected {sorted(expected_providers)}",
                    line.strip(),
                )
            )
    return issues


def _check_command_counts(
    path: str,
    line_no: int,
    line: str,
    expected_count: int,
) -> list[Issue]:
    issues: list[Issue] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern in COMMAND_COUNT_PATTERNS:
        for match in pattern.finditer(line):
            if match.span() in seen_spans:
                continue
            seen_spans.add(match.span())
            value = _parse_number(match.group("num"))
            if value is not None and value != expected_count:
                issues.append(
                    Issue(
                        "command-count",
                        path,
                        line_no,
                        f"README says {value} commands, expected {expected_count}",
                        line.strip(),
                    )
                )
    return issues


def _check_command_names(
    path: str,
    line_no: int,
    line: str,
    command_set: set[str],
) -> list[Issue]:
    issues = []
    stripped = line.strip()
    matches = list(BACKTICK_ANTEMORTEM_COMMAND_RE.finditer(line))
    if bare_match := BARE_ANTEMORTEM_COMMAND_RE.search(stripped):
        matches.append(bare_match)
    for match in matches:
        command = match.group(1)
        if command not in command_set:
            issues.append(
                Issue(
                    "command-name",
                    path,
                    line_no,
                    f"`antemortem {command}` is not a registered CLI command",
                    line.strip(),
                )
            )
    return issues


def _check_command_lists(
    path: str,
    line_no: int,
    line: str,
    command_set: set[str],
) -> list[Issue]:
    if "command" not in line.lower():
        return []
    mentioned = {word for word in BACKTICK_WORD_RE.findall(line) if word in command_set}
    if len(mentioned) >= 2 and mentioned != command_set:
        return [
            Issue(
                "command-list",
                path,
                line_no,
                f"command list is {sorted(mentioned)}, expected {sorted(command_set)}",
                line.strip(),
            )
        ]
    return []


def _check_decision_labels(
    path: str,
    line_no: int,
    line: str,
    decision_labels: set[str],
) -> list[Issue]:
    issues = []
    for label in UPPER_LABEL_RE.findall(line):
        if label in OBSOLETE_DECISION_LABELS and label not in decision_labels:
            issues.append(
                Issue(
                    "decision-label",
                    path,
                    line_no,
                    f"{label} is not a current decision enum",
                    line.strip(),
                )
            )
    return issues


def _check_test_claims(path: str, line_no: int, line: str, expected_count: int) -> list[Issue]:
    issues = []
    for match in TOTAL_TEST_CLAIM_RE.finditer(line):
        count = int(match.group("count"))
        issues.append(
            Issue(
                "test-count",
                path,
                line_no,
                f"exact public test count `{count}` is platform-dependent; use `python -m pytest -q` instead",
                line.strip(),
            )
        )
    return issues


def _check_package_name(path: str, line_no: int, line: str, package_name: str) -> list[Issue]:
    if package_name == "antemortem-cli":
        return []
    stale_contexts = (
        r"pip\s+install\s+['\"]?antemortem-cli",
        r"pypi\.org/project/antemortem-cli",
        r"PyPI name is\s+`?antemortem-cli`?",
        r"PyPI 이름은\s+`?antemortem-cli`?",
    )
    for pattern in stale_contexts:
        if re.search(pattern, line, flags=re.I):
            return [
                Issue(
                    "package-name",
                    path,
                    line_no,
                    f"package install name is `{package_name}`, not `antemortem-cli`",
                    line.strip(),
                )
            ]
    return []


def _check_provider_matrix(path: str, text: str, expected_providers: set[str]) -> list[Issue]:
    heading_match = re.search(r"^## Provider support|^## Provider 지원", text, flags=re.M)
    if not heading_match:
        return []

    capability_names = _load_provider_capability_names()
    native_expected = set(expected_providers) - {"openai-compatible"}
    if native_expected != capability_names:
        return [
            Issue(
                "provider-matrix",
                path,
                0,
                f"provider factory names {sorted(native_expected)} do not match capability registry {sorted(capability_names)}",
                "src/antemortem/providers/capabilities.py",
            )
        ]

    language = "kr" if path.endswith("_KR.md") else "en"
    if _extract_provider_matrix_block(text) == _expected_provider_matrix_block(language):
        return []
    line_no = text[: heading_match.start()].count("\n") + 1
    return [
        Issue(
            "provider-matrix",
            path,
            line_no,
            "provider support matrix does not match provider capability registry",
            "run python scripts/check_repo_consistency.py after updating provider capabilities",
        )
    ]


def _check_provider_compatibility_doc(root: Path) -> list[Issue]:
    rel = "docs/provider_compatibility.md"
    path = root / rel
    if not path.exists():
        return [Issue("provider-matrix", rel, 0, "provider compatibility doc is missing", rel)]
    text = path.read_text(encoding="utf-8")
    if _extract_provider_matrix_block(text) == _expected_provider_matrix_block("en"):
        return []
    return [
        Issue(
            "provider-matrix",
            rel,
            1,
            "provider compatibility doc matrix does not match provider capability registry",
            "docs/provider_compatibility.md",
        )
    ]


def _extract_provider_matrix_block(text: str) -> str | None:
    start = text.find(PROVIDER_MATRIX_START)
    end = text.find(PROVIDER_MATRIX_END)
    if start == -1 or end == -1 or end < start:
        return None
    return text[start : end + len(PROVIDER_MATRIX_END)].replace("\r\n", "\n")


def _expected_provider_matrix_block(language: str) -> str:
    _ensure_src_on_path(Path(__file__).resolve().parents[1])
    from antemortem.providers.capabilities import render_provider_matrix

    return (
        PROVIDER_MATRIX_START
        + "\n"
        + render_provider_matrix(language)
        + "\n"
        + PROVIDER_MATRIX_END
    )


def _load_provider_capability_names() -> set[str]:
    _ensure_src_on_path(Path(__file__).resolve().parents[1])
    from antemortem.providers.capabilities import native_provider_names

    return set(native_provider_names())


def _load_pyproject(root: Path) -> dict:
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))


def _load_cli_commands(root: Path) -> list[str]:
    _ensure_src_on_path(root)
    from antemortem.cli import app

    return sorted(
        info.name or info.callback.__name__.replace("_", "-")
        for info in app.registered_commands
        if info.callback is not None
    )


def _load_decision_labels(root: Path) -> tuple[str, ...]:
    _ensure_src_on_path(root)
    from antemortem.decision import DECISION_LABELS

    return tuple(DECISION_LABELS)


def _load_supported_providers(root: Path) -> tuple[str, ...]:
    _ensure_src_on_path(root)
    from antemortem.providers.factory import supported_providers

    return tuple(sorted(supported_providers()))


def _ensure_src_on_path(root: Path) -> None:
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def _decode_provider_badge(raw: str) -> set[str]:
    decoded = unquote(raw).replace("--", "-").lower()
    return {part.strip() for part in decoded.split("|") if part.strip()}


def _parse_number(raw: str) -> int | None:
    if raw.isdigit():
        return int(raw)
    return NUMBER_WORDS.get(raw.lower())


def _version_tuple(raw: str) -> tuple[int, int, int]:
    parts = [int(part) for part in raw.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _check_generated_claim_docs(root: Path, claim_facts: object | None = None) -> list[Issue]:
    generator = _load_claim_generator()
    facts = claim_facts or generator.collect_claim_facts(root)
    issues: list[Issue] = []
    for rel_path, expected in generator.expected_outputs(facts).items():
        path = root / rel_path
        rel = str(rel_path).replace("\\", "/")
        if not path.exists():
            issues.append(
                Issue(
                    "generated-claims",
                    rel,
                    0,
                    "generated README claim block is missing",
                    f"run {Path('scripts/generate_readme_claims.py')} --write",
                )
            )
            continue
        actual = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        if actual != expected:
            issues.append(
                Issue(
                    "generated-claims",
                    rel,
                    1,
                    "generated README claim block is stale",
                    "run python scripts/generate_readme_claims.py --write",
                )
            )
    return issues


def _check_generated_claim_references(root: Path, readme_files: Iterable[str]) -> list[Issue]:
    issues: list[Issue] = []
    for rel in readme_files:
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "docs/generated/claims.md" in text and "docs/generated/claims_kr.md" in text:
            continue
        issues.append(
            Issue(
                "generated-claims",
                rel,
                0,
                "README does not reference generated claim blocks",
                "docs/generated/claims.md and docs/generated/claims_kr.md",
            )
        )
    return issues


def _load_claim_generator():
    path = Path(__file__).with_name("generate_readme_claims.py")
    spec = importlib.util.spec_from_file_location("generate_readme_claims", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help="TOML allowlist for legitimate historical README references.",
    )
    args = parser.parse_args(argv)

    issues = check_repository(args.root, allowlist_path=args.allowlist)
    if issues:
        for issue in issues:
            print(issue.format(), file=sys.stderr)
        print(f"\nRepository consistency check failed: {len(issues)} issue(s).", file=sys.stderr)
        return 1

    print("Repository consistency check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
