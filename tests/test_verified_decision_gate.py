# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Reviewer P0: citation verification runs BEFORE the decision gate.

Pre-fix:
  classification → coverage check → evidence_sha256 → critic → decision

Citations weren't verified inside ``run`` — only ``lint`` checked them
later. So an artifact like this was producible:

  classifications: [
    {id: t1, label: GHOST, citation: \"src/auth.py:9999\", note: \"already mitigated\"}
  ]
  decision: SAFE_TO_PROCEED

Post-fix: ``audit_output_citations`` runs after coverage/evidence-hash
and before ``compute_decision``. If any non-UNRESOLVED finding has an
unresolvable citation, the decision is forced to ``NEEDS_MORE_EVIDENCE``
with a rationale that names the violations.

Same contract is enforced on the MCP path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from antemortem.citations import (
    CitationAudit,
    audit_output_citations,
)
from antemortem.schema import AntemortemOutput, Classification, NewTrap


def _output_with_bad_citation(line: int = 9999) -> AntemortemOutput:
    return AntemortemOutput(
        classifications=[
            Classification(
                id="t1", label="REAL",
                citation=f"src/auth.py:{line}", note="x",
            ),
        ],
    )


def _output_clean() -> AntemortemOutput:
    return AntemortemOutput(
        classifications=[
            Classification(
                id="t1", label="REAL", citation="src/auth.py:5", note="x",
            ),
            Classification(
                id="t2", label="UNRESOLVED", citation=None, note="no evidence",
            ),
        ],
    )


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 21)) + "\n",
        encoding="utf-8",
    )
    return repo


# ---------------------------------------------------------------------------
# audit_output_citations: pure helper.
# ---------------------------------------------------------------------------


def test_audit_passes_on_valid_citations(tmp_path):
    repo = _make_repo(tmp_path)
    audit = audit_output_citations(_output_clean(), repo)
    assert audit.ok is True
    assert audit.violations == []
    # UNRESOLVED skipped, REAL with valid citation checked.
    assert audit.checked == 1


def test_audit_fails_when_line_out_of_range(tmp_path):
    repo = _make_repo(tmp_path)
    audit = audit_output_citations(_output_with_bad_citation(line=9999), repo)
    assert audit.ok is False
    assert len(audit.violations) == 1
    assert "out of range" in audit.violations[0]


def test_audit_fails_when_file_does_not_exist(tmp_path):
    repo = _make_repo(tmp_path)
    output = AntemortemOutput(
        classifications=[
            Classification(
                id="t1", label="GHOST",
                citation="src/missing.py:10", note="x",
            ),
        ],
    )
    audit = audit_output_citations(output, repo)
    assert audit.ok is False
    assert any("does not exist" in v for v in audit.violations)


def test_audit_skips_unresolved_findings(tmp_path):
    repo = _make_repo(tmp_path)
    output = AntemortemOutput(
        classifications=[
            Classification(
                id="t1", label="UNRESOLVED", citation=None, note="x",
            ),
        ],
    )
    audit = audit_output_citations(output, repo)
    assert audit.ok is True
    assert audit.checked == 0


def test_audit_includes_new_traps(tmp_path):
    repo = _make_repo(tmp_path)
    output = AntemortemOutput(
        new_traps=[
            NewTrap(id="t_new_1", hypothesis="x", citation="src/auth.py:9999"),
        ],
    )
    audit = audit_output_citations(output, repo)
    assert audit.ok is False
    assert any("t_new_1" in v for v in audit.violations)


# ---------------------------------------------------------------------------
# CLI run: invalid citation → NEEDS_MORE_EVIDENCE, never SAFE_TO_PROCEED.
# ---------------------------------------------------------------------------


from typer.testing import CliRunner
from unittest.mock import patch

from antemortem.cli import app


_DOC = """---
name: feat
date: 2026-04-21
template: basic
---

# Antemortem — feat

## 1. The change

Refactor the auth flow.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | token expiry | trap | 60% | n |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/auth.py`
"""


runner = CliRunner()


def _provider_returning(output: AntemortemOutput):
    from unittest.mock import MagicMock
    p = MagicMock()
    p.name = "anthropic"
    p.model = "mock"
    p.structured_complete.return_value = (output, {
        "input_tokens": 10, "output_tokens": 20,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
    })
    return p


def test_cli_run_forces_needs_more_evidence_on_invalid_citation(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    repo = _make_repo(tmp_path)
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")

    bad_output = AntemortemOutput(
        classifications=[
            Classification(
                id="t1", label="GHOST",
                citation="src/auth.py:9999", note="x",
            ),
        ],
    )

    with patch("antemortem.commands.run.make_provider", return_value=_provider_returning(bad_output)):
        runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])

    import json
    artifact = json.loads((tmp_path / "feat.json").read_text(encoding="utf-8"))
    # Decision flipped to NEEDS_MORE_EVIDENCE; rationale names the audit.
    assert artifact["decision"] == "NEEDS_MORE_EVIDENCE"
    assert "Citation audit failed" in artifact["decision_rationale"]


def test_cli_run_proceeds_normally_when_citations_clean(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    repo = _make_repo(tmp_path)
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")

    good_output = AntemortemOutput(
        classifications=[
            Classification(
                id="t1", label="GHOST",
                citation="src/auth.py:5", note="already mitigated",
            ),
        ],
    )

    with patch("antemortem.commands.run.make_provider", return_value=_provider_returning(good_output)):
        runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])

    import json
    artifact = json.loads((tmp_path / "feat.json").read_text(encoding="utf-8"))
    # Decision is whatever compute_decision normally produces — not
    # forced to NEEDS_MORE_EVIDENCE by the citation audit.
    assert artifact["decision"] != "NEEDS_MORE_EVIDENCE" or (
        "Citation audit failed" not in artifact["decision_rationale"]
    )


# ---------------------------------------------------------------------------
# MCP run: same contract.
# ---------------------------------------------------------------------------


def test_mcp_run_forces_needs_more_evidence_on_invalid_citation(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    repo = _make_repo(tmp_path)
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")

    from antemortem.mcp.server import run as mcp_run

    bad_output = AntemortemOutput(
        classifications=[
            Classification(
                id="t1", label="REAL",
                citation="src/auth.py:9999", note="x",
            ),
        ],
    )
    with patch("antemortem.mcp.server.make_provider", return_value=_provider_returning(bad_output)):
        result = mcp_run(document=str(doc_path), repo=str(repo))

    assert result["decision"] == "NEEDS_MORE_EVIDENCE"
    assert "Citation audit failed" in result["rationale"]
    # Audit summary surfaces in the MCP response so agents can branch on it.
    assert "citation_audit" in result
    assert result["citation_audit"]["ok"] is False


def test_mcp_run_normal_decision_when_citations_clean(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    repo = _make_repo(tmp_path)
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")

    from antemortem.mcp.server import run as mcp_run

    good_output = AntemortemOutput(
        classifications=[
            Classification(
                id="t1", label="GHOST",
                citation="src/auth.py:5", note="x",
            ),
        ],
    )
    with patch("antemortem.mcp.server.make_provider", return_value=_provider_returning(good_output)):
        result = mcp_run(document=str(doc_path), repo=str(repo))

    assert result["citation_audit"]["ok"] is True
    # Whatever the decision is, it's not the citation-audit force path:
    if result["decision"] == "NEEDS_MORE_EVIDENCE":
        assert "Citation audit" not in result.get("rationale", "")
