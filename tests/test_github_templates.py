"""Checks for trust-focused GitHub issue and PR templates."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISSUE_TEMPLATE = ROOT / ".github" / "ISSUE_TEMPLATE"
REQUIRED_ISSUE_FILES = {
    "bug_report.yml",
    "feature_request.yml",
    "consistency_drift.yml",
}
REQUIRED_FIELDS = {
    "Command run",
    "Expected behavior",
    "Actual behavior",
    "antemortem version",
    "OS and Python version",
    "provider calls",
    "Minimal repro",
    "python scripts/check_repo_consistency.py",
    "Benchmark or lint artifact",
}
REQUIRED_PR_CHECKS = {
    "Tests added or updated.",
    "Docs updated when behavior or public claims changed.",
    "README claims are backed by source, tests, generated artifacts, benchmark output, or reproducible commands.",
    "No citation validation, evidence-bound citation checks, schema validation, path traversal protections, provider error handling, or offline benchmark behavior was weakened.",
    "No live API dependency was added to normal CI.",
    "Release audit run, or reason documented:",
}


def test_issue_templates_exist():
    assert {path.name for path in ISSUE_TEMPLATE.glob("*.yml")} == REQUIRED_ISSUE_FILES


def test_issue_templates_collect_trust_context():
    for filename in REQUIRED_ISSUE_FILES:
        text = (ISSUE_TEMPLATE / filename).read_text(encoding="utf-8")
        for field in REQUIRED_FIELDS:
            assert field in text, f"{filename} missing {field!r}"


def test_pull_request_template_trust_checklist():
    text = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    for check in REQUIRED_PR_CHECKS:
        assert check in text
