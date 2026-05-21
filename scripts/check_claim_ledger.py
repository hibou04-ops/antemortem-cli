# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Validate the public README claim ledger."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


README_FILES = (
    "README.md",
    "README_KR.md",
    "EASY_README.md",
    "EASY_README_KR.md",
)
LEDGER_FILES = ("docs/claim_ledger.md", "docs/claim_ledger_kr.md")
EXPECTED_HEADERS = ("Claim", "Location", "Source of truth", "Verification command", "Status")
ALLOWED_STATUSES = {
    "source-backed",
    "test-backed",
    "benchmark-backed",
    "generated",
    "command-backed",
    "qualitative",
}
REQUIRED_CLAIM_KEYWORDS = (
    "version",
    "command list",
    "decision labels",
    "benchmark metrics",
    "provider support",
    "evidence-bound citation",
    "release hygiene",
)
SOURCE_PATH_RE = re.compile(
    r"(?<![\w/.-])("
    r"(?:src|tests|docs|scripts|benchmarks|examples|\.github)/[A-Za-z0-9_./-]+"
    r"|pyproject\.toml|CHANGELOG\.md"
    r")"
)
COMMAND_RE = re.compile(r"^(python|pytest|antemortem)\b")


@dataclass(frozen=True)
class LedgerRow:
    claim: str
    location: str
    source: str
    verification: str
    status: str
    path: str
    line: int


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    line: int
    message: str

    def format(self) -> str:
        location = f"{self.path}:{self.line}" if self.line else self.path
        return f"{location}: [{self.code}] {self.message}"


def check_claim_ledger(
    root: Path,
    *,
    ledger_files: Sequence[str] = LEDGER_FILES,
    readme_files: Sequence[str] = README_FILES,
    check_required: bool = True,
) -> list[Issue]:
    root = root.resolve()
    issues: list[Issue] = []
    rows: list[LedgerRow] = []

    for rel in ledger_files:
        path = root / rel
        if not path.exists():
            issues.append(Issue("missing-ledger", rel, 0, "claim ledger file is missing"))
            continue
        parsed_rows, parse_issues = _parse_ledger(path, rel)
        rows.extend(parsed_rows)
        issues.extend(parse_issues)

    for row in rows:
        issues.extend(_validate_row(root, row))

    if check_required:
        issues.extend(_check_required_coverage(rows))
        issues.extend(_check_readme_references(root, readme_files))
    return issues


def _parse_ledger(path: Path, rel: str) -> tuple[list[LedgerRow], list[Issue]]:
    rows: list[LedgerRow] = []
    issues: list[Issue] = []
    in_table = False
    headers_seen = False

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = _split_markdown_row(line)
        if not cells:
            continue
        if tuple(cells) == EXPECTED_HEADERS:
            in_table = True
            headers_seen = True
            continue
        if not in_table:
            continue
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        if len(cells) != len(EXPECTED_HEADERS):
            issues.append(
                Issue(
                    "ledger-format",
                    rel,
                    line_no,
                    f"expected {len(EXPECTED_HEADERS)} cells, found {len(cells)}",
                )
            )
            continue
        rows.append(
            LedgerRow(
                claim=cells[0],
                location=cells[1],
                source=cells[2],
                verification=cells[3],
                status=cells[4],
                path=rel,
                line=line_no,
            )
        )

    if not headers_seen:
        issues.append(
            Issue(
                "ledger-format",
                rel,
                0,
                "missing claim ledger table with required headers",
            )
        )
    if headers_seen and not rows:
        issues.append(Issue("ledger-format", rel, 0, "claim ledger has no rows"))
    return rows, issues


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip().replace("\\|", "|") for cell in stripped.split("|")]


def _validate_row(root: Path, row: LedgerRow) -> list[Issue]:
    issues: list[Issue] = []
    fields = {
        "Claim": row.claim,
        "Location": row.location,
        "Source of truth": row.source,
        "Verification command": row.verification,
        "Status": row.status,
    }
    for name, value in fields.items():
        if not value:
            issues.append(Issue("missing-field", row.path, row.line, f"{name} is empty"))

    if row.status not in ALLOWED_STATUSES:
        issues.append(
            Issue(
                "invalid-status",
                row.path,
                row.line,
                f"Status `{row.status}` is not one of {sorted(ALLOWED_STATUSES)}",
            )
        )
    if "qualitative" in row.source.lower() and row.status != "qualitative":
        issues.append(
            Issue(
                "qualitative-unmarked",
                row.path,
                row.line,
                "qualitative claim source must use Status `qualitative`",
            )
        )
    if row.status == "qualitative" and "qualitative" not in row.source.lower():
        issues.append(
            Issue(
                "qualitative-source",
                row.path,
                row.line,
                "Status `qualitative` requires Source of truth to say qualitative",
            )
        )
    if row.status != "qualitative" and not _has_backing_source(row.source):
        issues.append(
            Issue(
                "unbacked-claim",
                row.path,
                row.line,
                "non-qualitative claim has no source code, test, benchmark, generated doc, or command source",
            )
        )

    issues.extend(_validate_source_paths(root, row))
    issues.extend(_validate_locations(root, row))
    if not _valid_verification(row.verification):
        issues.append(
            Issue(
                "verification-command",
                row.path,
                row.line,
                "verification command must be a reproducible command or explicit qualitative marker",
            )
        )
    return issues


def _has_backing_source(source: str) -> bool:
    lowered = source.lower()
    return bool(
        SOURCE_PATH_RE.search(source)
        or "benchmark output" in lowered
        or "generated doc" in lowered
        or "reproducible command" in lowered
        or COMMAND_RE.search(source.strip())
    )


def _validate_source_paths(root: Path, row: LedgerRow) -> list[Issue]:
    issues: list[Issue] = []
    for raw_path in SOURCE_PATH_RE.findall(row.source):
        candidate = root / raw_path
        if not candidate.exists():
            issues.append(
                Issue(
                    "missing-source",
                    row.path,
                    row.line,
                    f"source path does not exist: {raw_path}",
                )
            )
    return issues


def _validate_locations(root: Path, row: LedgerRow) -> list[Issue]:
    issues: list[Issue] = []
    for location in _split_locations(row.location):
        path_text, fragment = _split_location(location)
        path = root / path_text
        if not path.exists():
            issues.append(
                Issue("missing-location", row.path, row.line, f"location file does not exist: {path_text}")
            )
            continue
        if fragment:
            text = path.read_text(encoding="utf-8")
            if fragment not in text:
                issues.append(
                    Issue(
                        "location-drift",
                        row.path,
                        row.line,
                        f"location fragment not found in {path_text}: {fragment}",
                    )
                )
    return issues


def _split_locations(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split("<br>") if part.strip())


def _split_location(location: str) -> tuple[str, str]:
    for readme in README_FILES:
        prefix = readme + ":"
        if location.startswith(prefix):
            return readme, location[len(prefix) :].strip()
        if location == readme:
            return readme, ""
    if ":" in location:
        path, fragment = location.split(":", 1)
        return path.strip(), fragment.strip()
    return location.strip(), ""


def _valid_verification(command: str) -> bool:
    stripped = command.strip()
    return bool(stripped == "n/a qualitative" or COMMAND_RE.search(stripped))


def _check_required_coverage(rows: Sequence[LedgerRow]) -> list[Issue]:
    combined_claims = "\n".join(row.claim.lower() for row in rows)
    combined_locations = "\n".join(row.location for row in rows)
    issues: list[Issue] = []
    for keyword in REQUIRED_CLAIM_KEYWORDS:
        if keyword not in combined_claims:
            issues.append(
                Issue(
                    "missing-required-claim",
                    "claim ledger",
                    0,
                    f"required claim category is not represented: {keyword}",
                )
            )
    for readme in README_FILES:
        if readme not in combined_locations:
            issues.append(
                Issue(
                    "missing-readme-coverage",
                    "claim ledger",
                    0,
                    f"no ledger row references {readme}",
                )
            )
    return issues


def _check_readme_references(root: Path, readme_files: Iterable[str]) -> list[Issue]:
    issues: list[Issue] = []
    for readme in readme_files:
        path = root / readme
        if not path.exists():
            issues.append(Issue("missing-readme", readme, 0, "README variant is missing"))
            continue
        text = path.read_text(encoding="utf-8")
        for ledger in LEDGER_FILES:
            if ledger not in text:
                issues.append(
                    Issue(
                        "missing-ledger-reference",
                        readme,
                        0,
                        f"README variant does not reference {ledger}",
                    )
                )
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)

    issues = check_claim_ledger(args.root)
    if issues:
        for issue in issues:
            print(issue.format(), file=sys.stderr)
        print(f"\nClaim ledger check failed: {len(issues)} issue(s).", file=sys.stderr)
        return 1

    print("Claim ledger check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
