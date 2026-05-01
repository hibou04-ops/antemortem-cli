# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Tests for parser_contract / schema_version frontmatter contract.

Reviewer's recommendation:
> Schema version and template version should be explicitly bound. v1.0
> contract requires this:
>   template: basic
>   schema_version: 0.6
>   parser_contract: antemortem-v1

`antemortem init` now emits these. `antemortem lint` validates them
when present and stays silent when missing (older docs round-trip).
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from antemortem._versions import (
    KNOWN_TEMPLATE_LABELS,
    PARSER_CONTRACT,
    SCHEMA_VERSION,
    SUPPORTED_PARSER_CONTRACTS,
    SUPPORTED_SCHEMA_VERSIONS,
)
from antemortem.cli import app
from antemortem.parser import parse_document

runner = CliRunner()


# ---------------------------------------------------------------------------
# init scaffolds the version fields.
# ---------------------------------------------------------------------------


def test_init_emits_schema_version_and_parser_contract(tmp_path: Path):
    out_dir = tmp_path / "antemortem"
    result = runner.invoke(
        app,
        ["init", "feat", "--output-dir", str(out_dir)],
    )
    assert result.exit_code == 0, result.stdout
    doc_path = out_dir / "feat.md"
    text = doc_path.read_text(encoding="utf-8")
    assert f'schema_version: "{SCHEMA_VERSION}"' in text
    assert f"parser_contract: {PARSER_CONTRACT}" in text


def test_init_enhanced_template_also_emits_versions(tmp_path: Path):
    out_dir = tmp_path / "antemortem"
    result = runner.invoke(
        app,
        ["init", "feat", "--enhanced", "--output-dir", str(out_dir)],
    )
    assert result.exit_code == 0
    text = (out_dir / "feat.md").read_text(encoding="utf-8")
    assert "schema_version" in text
    assert "parser_contract" in text


def test_parser_round_trips_versions(tmp_path: Path):
    """Round-trip: write via init, parse, fields appear in frontmatter."""
    out_dir = tmp_path / "antemortem"
    runner.invoke(app, ["init", "feat", "--output-dir", str(out_dir)])
    doc = parse_document(out_dir / "feat.md")
    assert doc.frontmatter.schema_version == SCHEMA_VERSION
    assert doc.frontmatter.parser_contract == PARSER_CONTRACT


# ---------------------------------------------------------------------------
# lint validates contracts when present.
# ---------------------------------------------------------------------------


def _doc_with_versions(
    schema_version: str | None = SCHEMA_VERSION,
    parser_contract: str | None = PARSER_CONTRACT,
    template: str = "basic",
) -> str:
    sv = f'\nschema_version: "{schema_version}"' if schema_version else ""
    pc = f"\nparser_contract: {parser_contract}" if parser_contract else ""
    return f"""---
name: feat
date: 2026-04-21
template: {template}{sv}{pc}
---

# Antemortem — feat

## 1. The change

Refactor.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | x | trap | 50% | n |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/auth.py`
"""


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text("a\n" * 20, encoding="utf-8")
    return repo


def test_lint_passes_on_current_versions(tmp_path: Path):
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_doc_with_versions(), encoding="utf-8")
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["lint", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 0


def test_lint_passes_when_versions_omitted_legacy_doc(tmp_path: Path):
    """Older docs without the new fields stay valid — backward compat."""
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(
        _doc_with_versions(schema_version=None, parser_contract=None),
        encoding="utf-8",
    )
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["lint", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 0, result.stdout


def test_lint_fails_on_unknown_parser_contract(tmp_path: Path):
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(
        _doc_with_versions(parser_contract="antemortem-v999"),
        encoding="utf-8",
    )
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["lint", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 1
    assert "parser_contract" in result.stderr
    assert "antemortem-v999" in result.stderr


def test_lint_fails_on_unknown_schema_version(tmp_path: Path):
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(
        _doc_with_versions(schema_version="99.99"),
        encoding="utf-8",
    )
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["lint", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 1
    assert "schema_version" in result.stderr


def test_lint_fails_on_unknown_template(tmp_path: Path):
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(
        _doc_with_versions(template="experimental"),
        encoding="utf-8",
    )
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["lint", str(doc_path), "--repo", str(repo)])
    assert result.exit_code == 1
    assert "template" in result.stderr


# ---------------------------------------------------------------------------
# Sanity: SUPPORTED_* sets are populated and contain current value.
# ---------------------------------------------------------------------------


def test_current_versions_are_in_supported_sets():
    assert PARSER_CONTRACT in SUPPORTED_PARSER_CONTRACTS
    assert SCHEMA_VERSION in SUPPORTED_SCHEMA_VERSIONS


def test_known_templates_includes_basic_and_enhanced():
    assert "basic" in KNOWN_TEMPLATE_LABELS
    assert "enhanced" in KNOWN_TEMPLATE_LABELS
