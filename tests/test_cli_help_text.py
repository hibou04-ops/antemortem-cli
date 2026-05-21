"""CLI help, exit-code, and actionable-error message contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from antemortem.cli import app
from antemortem import exit_codes


runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "benchmarks" / "golden_cases"

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


HELP_SNAPSHOTS = {
    "root": {
        "args": ["--help"],
        "usage": "Usage: antemortem [OPTIONS] COMMAND [ARGS]...",
        "summary": "Pre-diff risk verification against repository evidence.",
        "tokens": ("--version", "init", "doctor", "run", "lint", "evidence", "gate", "eval"),
    },
    "init": {
        "args": ["init", "--help"],
        "usage": "Usage: antemortem init [OPTIONS] NAME",
        "summary": "Create a recon markdown document.",
        "tokens": ("--enhanced", "--output-dir", "--force"),
    },
    "doctor": {
        "args": ["doctor", "--help"],
        "usage": "Usage: antemortem doctor [OPTIONS] DOCUMENT",
        "summary": "Preview parsed input and file payload.",
        "tokens": ("--repo", "--json", "--show-files", "--show-payload-preview", "--strict"),
    },
    "run": {
        "args": ["run", "--help"],
        "usage": "Usage: antemortem run [OPTIONS] DOCUMENT",
        "summary": "Classify traps with a provider and write an artifact.",
        "tokens": ("--provider", "--model", "--base-url", "--critic", "--strict-citations"),
    },
    "lint": {
        "args": ["lint", "--help"],
        "usage": "Usage: antemortem lint [OPTIONS] DOCUMENT",
        "summary": "Validate schema, citations, and evidence bindings.",
        "tokens": ("--repo", "--strict-evidence"),
    },
    "evidence": {
        "args": ["evidence", "--help"],
        "usage": "Usage: antemortem evidence [OPTIONS] ARTIFACT",
        "summary": "Inspect or fill artifact evidence hashes.",
        "tokens": ("--repo", "--check", "--write-missing", "--show-snippets", "--json"),
    },
    "gate": {
        "args": ["gate", "--help"],
        "usage": "Usage: antemortem gate [OPTIONS] DOCUMENT",
        "summary": "Enforce lint and decision policy for CI.",
        "tokens": ("--repo", "--allow", "--require-artifact"),
    },
    "eval": {
        "args": ["eval", "--help"],
        "usage": "Usage: antemortem eval [OPTIONS] PATH",
        "summary": "Measure offline golden benchmark cases.",
        "tokens": ("--json", "--fail-under"),
    },
}


def _plain(text: str) -> str:
    text = ANSI_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def test_help_output_snapshots_cover_every_command():
    registered = {
        info.name or info.callback.__name__.replace("_", "-")
        for info in app.registered_commands
        if info.callback is not None
    }
    assert set(HELP_SNAPSHOTS) == registered | {"root"}

    for snapshot in HELP_SNAPSHOTS.values():
        result = runner.invoke(
            app,
            snapshot["args"],
            color=False,
            env={"COLUMNS": "220"},
        )
        assert result.exit_code == 0, result.output
        help_text = _plain(result.stdout)
        assert snapshot["usage"] in help_text
        assert snapshot["summary"] in help_text
        for token in snapshot["tokens"]:
            assert token in help_text


def test_readme_quick_start_commands_match_cli_help():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = readme.split("## Quick start", 1)[1].split("## How is this different?", 1)[0]
    commands = {
        match.group(1)
        for match in re.finditer(r"^antemortem\s+([a-z][a-z0-9_-]*)\b", quick_start, re.M)
    }
    help_text = _plain(runner.invoke(app, ["--help"], color=False).stdout)

    assert commands == {"init", "doctor", "run", "lint", "gate"}
    for command in commands:
        assert re.search(rf"\b{command}\b", help_text)


def test_validation_failures_explain_why_and_next_command(tmp_path: Path, monkeypatch):
    bad_doc = tmp_path / "bad.md"
    bad_doc.write_text("# Missing frontmatter\n", encoding="utf-8")

    init_result = runner.invoke(app, ["init", "../bad", "--output-dir", str(tmp_path)])
    lint_result = runner.invoke(app, ["lint", str(bad_doc), "--repo", str(tmp_path)])

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    run_result = runner.invoke(app, ["run", str(bad_doc), "--repo", str(tmp_path)])

    for result in (init_result, lint_result, run_result):
        output = result.stdout + result.stderr
        assert result.exit_code != 0
        assert "FAIL:" in output
        assert "Why:" in output
        assert "Next:" in output


def test_policy_failures_explain_why_and_next_command(tmp_path: Path):
    doc = tmp_path / "feat.md"
    doc.write_text(
        "---\nname: feat\ndate: 2026-04-21\ntemplate: basic\n---\n\n"
        "# Antemortem\n\n## 1. The change\n\nx\n\n"
        "## 2. Traps hypothesized\n\n"
        "| # | trap | label | P(issue) | notes |\n"
        "|---|------|-------|----------|-------|\n"
        "| 1 | x | trap | 50% | n |\n\n"
        "## 3. Recon protocol\n\n- `src/auth.py`\n",
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "auth.py").write_text("line 1\nline 2\n", encoding="utf-8")
    doc.with_suffix(".json").write_text(
        json.dumps(
            {
                "classifications": [
                    {"id": "t1", "label": "REAL", "citation": "src/auth.py:1", "note": "n"}
                ],
                "new_traps": [],
                "spec_mutations": [],
                "decision": "DO_NOT_PROCEED",
                "decision_rationale": "test",
            }
        ),
        encoding="utf-8",
    )

    gate_result = runner.invoke(app, ["gate", str(doc), "--repo", str(repo)])
    eval_result = runner.invoke(
        app,
        ["eval", str(GOLDEN), "--fail-under", "citation_valid_rate=1.0"],
    )

    for result in (gate_result, eval_result):
        output = result.stdout + result.stderr
        assert result.exit_code == exit_codes.POLICY_GATE_FAILURE
        assert "FAIL:" in output
        assert "Why:" in output
        assert "Next:" in output


def test_exit_code_documentation_matches_constants():
    docs = (ROOT / "docs" / "cli_exit_codes.md").read_text(encoding="utf-8")

    for value in (
        exit_codes.SUCCESS,
        exit_codes.VALIDATION_FAILURE,
        exit_codes.USAGE_ERROR,
        exit_codes.PROVIDER_FAILURE,
        exit_codes.POLICY_GATE_FAILURE,
        exit_codes.INTERNAL_ERROR,
    ):
        assert f"| {value} |" in docs
