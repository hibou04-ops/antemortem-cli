# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Check public docs for release-scope drift.

The next release is scoped to verification and release hygiene. This checker is
offline and deterministic: it scans public markdown for new-feature promises,
unimplemented command names, roadmap claims written as current features, and
comparative hype claims.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


README_FILES = (
    "README.md",
    "README_KR.md",
    "EASY_README.md",
    "EASY_README_KR.md",
)

DEFAULT_DOC_GLOBS = (
    "README.md",
    "README_KR.md",
    "EASY_README.md",
    "EASY_README_KR.md",
    "docs/*.md",
)

EXCLUDED_DOC_PARTS = {
    "docs/generated",
}

PROMISE_PATTERNS = (
    re.compile(r"\bcoming[- ]soon\b", re.I),
    re.compile(r"\bsoon\s+(?:add|adds|support|supports|ship|ships|include|includes)\b", re.I),
    re.compile(r"\bwill\s+(?:add|support|ship|include|provide|launch|release)\b", re.I),
    re.compile(r"\bplanned\s+(?:feature|support|command|integration|release)\b", re.I),
    re.compile(r"\bnext\s+release\s+will\b", re.I),
)

CURRENT_FEATURE_PATTERNS = (
    re.compile(r"\bnow\s+(?:supports|includes|provides|ships)\b", re.I),
    re.compile(r"\bcurrently\s+(?:supports|includes|provides|ships)\b", re.I),
    re.compile(r"\bavailable\s+(?:now|today)\b", re.I),
)

SUPERIORITY_PATTERNS = (
    re.compile(r"\bbest\b", re.I),
    re.compile(r"\bsuperior(?:ity)?\b", re.I),
    re.compile(r"\boutperform(?:s|ed|ing)?\b", re.I),
    re.compile(r"\bunbeatable\b", re.I),
    re.compile(r"\brevolutionary\b", re.I),
    re.compile(r"\bproduction-proven\b", re.I),
    re.compile(r"\benterprise-ready\b", re.I),
    re.compile(r"\bindustry-leading\b", re.I),
    re.compile(r"\bstate-of-the-art\b", re.I),
    re.compile(r"최고"),
    re.compile(r"우월"),
)

BACKTICK_ANTEMORTEM_COMMAND_RE = re.compile(r"`antemortem\s+([a-z][a-z0-9_-]*)\b[^`]*`", re.I)
LINE_ANTEMORTEM_COMMAND_RE = re.compile(r"^\s*(?:\$ )?antemortem\s+([a-z][a-z0-9_-]*)\b")
HYPHEN_COMMAND_RE = re.compile(
    r"(?:`([a-z][a-z0-9]*-[a-z0-9_-]+)`\s+command\b)"
    r"|(?:\b(?:add|new|planned|deferred)\s+(?:an?\s+)?([a-z][a-z0-9]*-[a-z0-9_-]+)\s+command\b)",
    re.I,
)
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
BOLD_HEADING_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")

ROADMAP_HEADINGS = (
    "roadmap",
    "next measurement track",
    "v1.0",
    "deferred",
    "future",
    "out of scope",
    "explicitly out of scope",
    "deferred work",
    "status & roadmap",
    "계약 lock",
    "명시적 out of scope",
)

BOUNDARY_PHRASES = (
    "no superiority",
    "not superiority",
    "not a superiority",
    "not claims of superiority",
    "not claim superiority",
    "does not claim",
    "do not claim",
    "no adoption",
    "not an ai code review replacement",
    "not comparative",
    "no comparative",
    "주장하지",
    "하지 않습니다",
    "안 됩니다",
    "아닙니다",
    "아니다",
)

DEFERRED_MARKERS = (
    "deferred",
    "later",
    "future",
    "roadmap",
    "only after",
    "after",
    "not current",
    "not shipped",
    "v1.0",
    "planned work",
    "보류",
    "이후",
    "나중",
    "계획",
)


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


def check_scope_freeze(
    root: Path,
    *,
    public_docs: Sequence[str] | None = None,
    commands: Iterable[str] | None = None,
    allowlist_path: Path | None = None,
) -> list[Issue]:
    root = root.resolve()
    command_set = set(commands or _load_cli_commands(root))
    docs = tuple(public_docs or _discover_public_docs(root))
    allowlist = _load_allowlist(allowlist_path or root / "scripts" / "scope_freeze_allowlist.toml")

    issues: list[Issue] = []
    for rel in docs:
        path = root / rel
        if not path.exists():
            issues.append(Issue("missing-doc", rel, 0, "public documentation file is missing", rel))
            continue
        issues.extend(_scan_doc(rel, path.read_text(encoding="utf-8"), command_set))

    return [issue for issue in issues if not any(entry.matches(issue) for entry in allowlist)]


def _scan_doc(path: str, text: str, command_set: set[str]) -> list[Issue]:
    issues: list[Issue] = []
    heading_stack: list[str] = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        heading = _extract_heading(line)
        if heading is not None:
            heading_stack = _update_heading_stack(heading_stack, heading)
        stripped = line.strip()
        if not stripped:
            continue

        roadmap_context = _is_roadmap_context(heading_stack)
        boundary_line = _is_boundary_line(stripped)

        if not roadmap_context and not boundary_line:
            for pattern in PROMISE_PATTERNS:
                if pattern.search(stripped):
                    issues.append(
                        Issue(
                            "feature-promise",
                            path,
                            line_no,
                            "feature promise is not allowed during the release scope freeze",
                            stripped,
                        )
                    )
                    break

        issues.extend(
            _check_command_names(path, line_no, stripped, command_set, roadmap_context=roadmap_context)
        )
        issues.extend(
            _check_current_roadmap_claim(
                path,
                line_no,
                stripped,
                roadmap_context=roadmap_context,
            )
        )
        if not boundary_line:
            issues.extend(_check_superiority(path, line_no, stripped))

    return issues


def _check_command_names(
    path: str,
    line_no: int,
    line: str,
    command_set: set[str],
    *,
    roadmap_context: bool,
) -> list[Issue]:
    issues: list[Issue] = []
    candidates = {match.group(1).lower() for match in BACKTICK_ANTEMORTEM_COMMAND_RE.finditer(line)}
    if match := LINE_ANTEMORTEM_COMMAND_RE.search(line):
        candidates.add(match.group(1).lower())
    for match in HYPHEN_COMMAND_RE.finditer(line):
        command = match.group(1) or match.group(2)
        if command:
            candidates.add(command.lower())
    for command in sorted(candidates):
        if command in command_set:
            continue
        if roadmap_context and _is_deferred_line(line):
            continue
        issues.append(
            Issue(
                "unimplemented-command",
                path,
                line_no,
                f"`{command}` is not a registered CLI command for this release",
                line,
            )
        )
    return issues


def _check_current_roadmap_claim(
    path: str,
    line_no: int,
    line: str,
    *,
    roadmap_context: bool,
) -> list[Issue]:
    lowered = line.lower()
    if roadmap_context or _is_boundary_line(line):
        return []
    if "roadmap" not in lowered and "future" not in lowered and "planned" not in lowered:
        return []
    for pattern in CURRENT_FEATURE_PATTERNS:
        if pattern.search(line):
            return [
                Issue(
                    "roadmap-as-current",
                    path,
                    line_no,
                    "roadmap language is written as a current shipped feature",
                    line,
                )
            ]
    return []


def _check_superiority(path: str, line_no: int, line: str) -> list[Issue]:
    for pattern in SUPERIORITY_PATTERNS:
        if pattern.search(line):
            return [
                Issue(
                    "superiority-claim",
                    path,
                    line_no,
                    "comparative quality or hype claim is not allowed during scope freeze",
                    line,
                )
            ]
    return []


def _discover_public_docs(root: Path) -> list[str]:
    docs: list[str] = []
    for pattern in DEFAULT_DOC_GLOBS:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if any(rel.startswith(part) for part in EXCLUDED_DOC_PARTS):
                continue
            docs.append(rel)
    return sorted(dict.fromkeys(docs))


def _extract_heading(line: str) -> str | None:
    if match := MARKDOWN_HEADING_RE.match(line):
        return match.group(2).strip()
    if match := BOLD_HEADING_RE.match(line.strip()):
        return match.group(1).strip()
    return None


def _update_heading_stack(stack: list[str], heading: str) -> list[str]:
    # Public docs mostly use flat short sections. Retaining recent headings is
    # enough to identify roadmap/deferred context without a markdown parser.
    return (stack + [heading])[-4:]


def _is_roadmap_context(headings: Sequence[str]) -> bool:
    combined = " / ".join(headings).lower()
    return any(token in combined for token in ROADMAP_HEADINGS)


def _is_boundary_line(line: str) -> bool:
    lowered = line.lower()
    return any(phrase in lowered for phrase in BOUNDARY_PHRASES)


def _is_deferred_line(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in DEFERRED_MARKERS)


def _load_allowlist(path: Path) -> tuple[AllowEntry, ...]:
    if not path.exists():
        return ()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    entries: list[AllowEntry] = []
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


def _load_cli_commands(root: Path) -> tuple[str, ...]:
    _ensure_src_on_path(root)
    from antemortem.cli import app

    return tuple(
        sorted(
            info.name or info.callback.__name__.replace("_", "-")
            for info in app.registered_commands
            if info.callback is not None
        )
    )


def _ensure_src_on_path(root: Path) -> None:
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help="TOML allowlist for deliberate deferred roadmap references.",
    )
    args = parser.parse_args(argv)

    issues = check_scope_freeze(args.root, allowlist_path=args.allowlist)
    if issues:
        for issue in issues:
            print(issue.format(), file=sys.stderr)
        print(f"\nScope freeze check failed: {len(issues)} issue(s).", file=sys.stderr)
        return 1

    print("Scope freeze check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
