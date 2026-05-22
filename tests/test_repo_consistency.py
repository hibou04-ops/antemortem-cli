# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Regression tests for README/source-of-truth consistency checks."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_repo_consistency.py"
SPEC = importlib.util.spec_from_file_location("check_repo_consistency", SCRIPT_PATH)
assert SPEC is not None
check_repo_consistency = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_repo_consistency
SPEC.loader.exec_module(check_repo_consistency)


FACTS = check_repo_consistency.RepositoryFacts(
    naming=check_repo_consistency.NamingFacts(
        repository_slug="hibou04-ops/antemortem-cli",
        repository_name="antemortem-cli",
        distribution_name="antemortem",
        import_package="antemortem",
        cli_command="antemortem",
    ),
    package_version="0.10.0",
    cli_commands=("doctor", "eval", "evidence", "gate", "init", "lint", "run"),
    decision_labels=(
        "SAFE_TO_PROCEED",
        "PROCEED_WITH_GUARDS",
        "NEEDS_MORE_EVIDENCE",
        "DO_NOT_PROCEED",
    ),
    providers=("anthropic", "gemini", "openai"),
    test_count=410,
)


def _check_readme(tmp_path: Path, text: str, *, allowlist: str | None = None):
    (tmp_path / "README.md").write_text(text, encoding="utf-8")
    allowlist_path = tmp_path / "allow.toml"
    if allowlist is not None:
        allowlist_path.write_text(allowlist, encoding="utf-8")
    return check_repo_consistency.check_repository(
        tmp_path,
        readme_files=("README.md",),
        allowlist_path=allowlist_path,
        facts=FACTS,
    )


def test_detects_version_mismatch(tmp_path: Path):
    issues = _check_readme(tmp_path, "Current release: v0.8.0\n")

    assert [issue.code for issue in issues] == ["stale-version"]
    assert "0.10.0" in issues[0].message


def test_detects_stale_decision_enum(tmp_path: Path):
    issues = _check_readme(
        tmp_path,
        "Decision gate: `PROCEED` / `PROCEED_WITH_GUARDS` / `BLOCK`.\n",
    )

    assert [issue.code for issue in issues] == ["decision-label", "decision-label"]
    assert {issue.message.split()[0] for issue in issues} == {"PROCEED", "BLOCK"}


def test_detects_stale_command_count(tmp_path: Path):
    issues = _check_readme(tmp_path, "A 3-command CLI for release hygiene.\n")

    assert [issue.code for issue in issues] == ["command-count"]
    assert "expected 7" in issues[0].message


def test_allows_historical_reference(tmp_path: Path):
    issues = _check_readme(
        tmp_path,
        "License history: v0.1.0 shipped before the Apache relicensing.\n",
        allowlist="""\
[[allow]]
code = "stale-version"
path = "README.md"
contains = "v0.1.0 shipped before the Apache relicensing"
reason = "Legitimate historical release note."
""",
    )

    assert issues == []


def test_rejects_exact_demo_test_count(tmp_path: Path):
    (tmp_path / "README.md").write_text("Current release: v0.10.0\n", encoding="utf-8")
    demo = tmp_path / "examples" / "_demo_output.txt"
    demo.parent.mkdir()
    demo.write_text("Apache 2.0 - 111 tests - offline demo\n", encoding="utf-8")

    issues = check_repo_consistency.check_repository(
        tmp_path,
        readme_files=("README.md",),
        proof_artifact_files=("examples/_demo_output.txt",),
        allowlist_path=tmp_path / "allow.toml",
        facts=FACTS,
    )

    assert [issue.code for issue in issues] == ["test-count"]
    assert issues[0].path == "examples/_demo_output.txt"
    assert "platform-dependent" in issues[0].message


def test_rejects_exact_test_count_badge(tmp_path: Path):
    issues = _check_readme(
        tmp_path,
        "[![Tests](https://img.shields.io/badge/tests-433%20passing-brightgreen.svg)](tests/)\n",
    )

    assert [issue.code for issue in issues] == ["test-count"]
    assert "nonnumeric CI verification badge" in issues[0].message


def test_allows_repository_title_that_differs_from_distribution_name(tmp_path: Path):
    issues = _check_readme(tmp_path, "# antemortem-cli\n")

    assert issues == []


def test_allows_distribution_import_and_cli_name_contexts(tmp_path: Path):
    issues = _check_readme(
        tmp_path,
        "Install with `pip install antemortem`.\n"
        "PyPI: https://pypi.org/project/antemortem/\n"
        "Import package: `import antemortem`.\n"
        "CLI executable: `antemortem --version`.\n",
    )

    assert issues == []


def test_requires_pypi_badge_and_install_to_use_distribution_name(tmp_path: Path):
    issues = _check_readme(
        tmp_path,
        "Install with `pip install antemortem-cli`.\n"
        "PyPI: https://pypi.org/project/antemortem-cli/\n",
    )

    assert [issue.code for issue in issues] == ["package-name", "package-name"]
    assert all("antemortem" in issue.message for issue in issues)


def test_requires_project_github_references_to_use_repository_slug(tmp_path: Path):
    issues = _check_readme(
        tmp_path,
        "Source: https://github.com/hibou04-ops/antemortem\n"
        "Correct: https://github.com/hibou04-ops/antemortem-cli\n",
    )

    assert [issue.code for issue in issues] == ["repository-name"]
    assert "hibou04-ops/antemortem-cli" in issues[0].message


def test_detects_stale_provider_matrix(tmp_path: Path):
    stale_matrix = """\
## Provider support

<!-- provider-matrix:start -->
| Provider | CLI |
|---|---|
| OpenAI | `--provider openai` |
<!-- provider-matrix:end -->
"""
    issues = _check_readme(tmp_path, stale_matrix)

    assert [issue.code for issue in issues] == ["provider-matrix"]
    assert "capability registry" in issues[0].message
