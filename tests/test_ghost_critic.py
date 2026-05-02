# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Reviewer P1: inverse-critic over GHOST findings.

False-GHOSTs (real risks waved through) are more dangerous than
false-REALs (cautious overlabel). Pre-fix the critic only reviewed
REAL/NEW. The new ``--critic-ghosts`` mode runs an inverse-critic
asking *is there credible evidence the risk is real after all?*

Modes:
- none (default) — backward-compat
- high — review high-severity OR low-confidence GHOSTs
- all — review every GHOST
"""
from __future__ import annotations

from typing import Any

import pytest

from antemortem.critic import (
    _ghost_findings_to_review,
    apply_critic_results,
    build_ghost_critic_payload,
    run_ghost_critic_pass,
)
from antemortem.schema import (
    AntemortemOutput,
    Classification,
    CriticResult,
)


def _output_with_ghosts(specs: list[dict[str, Any]]) -> AntemortemOutput:
    cls = []
    for s in specs:
        kwargs = {
            "id": s["id"],
            "label": s.get("label", "GHOST"),
            "citation": s.get("citation", "src/auth.py:5"),
            "note": s.get("note", "x"),
        }
        if "severity" in s:
            kwargs["severity"] = s["severity"]
        if "confidence" in s:
            kwargs["confidence"] = s["confidence"]
        cls.append(Classification(**kwargs))
    return AntemortemOutput(classifications=cls)


# ---------------------------------------------------------------------------
# _ghost_findings_to_review: mode-driven selection.
# ---------------------------------------------------------------------------


def test_mode_none_returns_empty_list():
    output = _output_with_ghosts(
        [{"id": "t1", "severity": "high"}, {"id": "t2", "confidence": 0.3}]
    )
    assert _ghost_findings_to_review(output, "none") == []


def test_mode_all_returns_every_ghost():
    output = _output_with_ghosts(
        [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}]
    )
    selected = _ghost_findings_to_review(output, "all")
    assert {c.id for c in selected} == {"t1", "t2", "t3"}


def test_mode_all_skips_non_ghost_classifications():
    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="GHOST", citation="src/a.py:1", note="x"),
            Classification(id="t2", label="REAL", citation="src/a.py:2", note="x"),
            Classification(id="t3", label="UNRESOLVED", citation=None, note="x"),
        ],
    )
    selected = _ghost_findings_to_review(output, "all")
    assert [c.id for c in selected] == ["t1"]


def test_mode_high_picks_high_severity():
    output = _output_with_ghosts(
        [
            {"id": "t1", "severity": "high"},
            {"id": "t2", "severity": "low"},
            {"id": "t3", "severity": "medium"},
        ]
    )
    selected = _ghost_findings_to_review(output, "high")
    assert [c.id for c in selected] == ["t1"]


def test_mode_high_picks_low_confidence():
    output = _output_with_ghosts(
        [
            {"id": "t1", "confidence": 0.3},  # below 0.7
            {"id": "t2", "confidence": 0.95},
            {"id": "t3"},  # no confidence
        ]
    )
    selected = _ghost_findings_to_review(output, "high")
    assert [c.id for c in selected] == ["t1"]


def test_mode_high_picks_either_signal():
    """OR semantics: high-severity OR low-confidence (each alone qualifies)."""
    output = _output_with_ghosts(
        [
            {"id": "t1", "severity": "high", "confidence": 0.99},
            {"id": "t2", "severity": "low", "confidence": 0.2},
        ]
    )
    selected = _ghost_findings_to_review(output, "high")
    assert {c.id for c in selected} == {"t1", "t2"}


# ---------------------------------------------------------------------------
# build_ghost_critic_payload structure.
# ---------------------------------------------------------------------------


def test_ghost_payload_has_ghosts_block():
    output = _output_with_ghosts(
        [{"id": "t1", "citation": "src/auth.py:5", "note": "already mitigated"}]
    )
    ghosts = _ghost_findings_to_review(output, "all")
    payload = build_ghost_critic_payload(
        spec="x",
        traps_table_md="| t1 | y |",
        files=[("src/auth.py", "line 1\nline 2\nline 3\nline 4\nline 5\n")],
        ghosts=ghosts,
    )
    assert "<ghosts>" in payload
    assert "id=t1" in payload
    assert "already mitigated" in payload


def test_ghost_payload_files_block_present():
    payload = build_ghost_critic_payload(
        spec="x",
        traps_table_md="| t1 |",
        files=[("a.py", "x = 1\n")],
        ghosts=[],
    )
    assert "<files>" in payload
    assert "a.py" in payload


# ---------------------------------------------------------------------------
# run_ghost_critic_pass: short-circuits when no ghosts to review.
# ---------------------------------------------------------------------------


def test_run_ghost_critic_short_circuits_in_none_mode():
    """None mode → empty result, no provider call."""
    from unittest.mock import MagicMock

    fake = MagicMock()
    fake.structured_complete.side_effect = AssertionError("provider should not be called")

    output = _output_with_ghosts([{"id": "t1"}])
    results, usage = run_ghost_critic_pass(
        provider=fake,
        spec="x",
        traps_table_md="| t1 |",
        files=[("a.py", "x\n")],
        first_pass=output,
        mode="none",
    )
    assert results == []
    assert usage["input_tokens"] == 0
    fake.structured_complete.assert_not_called()


def test_run_ghost_critic_short_circuits_when_no_ghosts():
    """High mode + no qualifying GHOSTs → no provider call."""
    from unittest.mock import MagicMock

    fake = MagicMock()
    fake.structured_complete.side_effect = AssertionError("should not be called")

    # All clean GHOSTs (no high severity, no low confidence)
    output = _output_with_ghosts([{"id": "t1", "confidence": 0.95}])
    results, usage = run_ghost_critic_pass(
        provider=fake,
        spec="x",
        traps_table_md="| t1 |",
        files=[("a.py", "x\n")],
        first_pass=output,
        mode="high",
    )
    assert results == []
    fake.structured_complete.assert_not_called()


# ---------------------------------------------------------------------------
# apply_critic_results: GHOST → REAL upgrade with counterevidence.
# ---------------------------------------------------------------------------


def test_apply_critic_upgrades_ghost_to_real_with_counterevidence():
    """The inverse-critic returns CONTRADICTED with recommended_label=REAL
    + counterevidence list. Apply path picks the first counterevidence
    cite as the new citation (the original GHOST cite supported the
    wrong direction)."""
    output = _output_with_ghosts(
        [{"id": "t1", "citation": "src/auth.py:5", "note": "already handled"}]
    )
    crit = CriticResult(
        finding_id="t1",
        status="CONTRADICTED",
        issues=["the cited mitigation is bypassed at line 12"],
        counterevidence=["src/auth.py:12"],
        recommended_label="REAL",
    )
    new_output = apply_critic_results(output, [crit])
    new_finding = next(c for c in new_output.classifications if c.id == "t1")
    assert new_finding.label == "REAL"
    assert new_finding.citation == "src/auth.py:12"  # counterevidence cite
    assert "ghost_contradicted" in new_finding.note


def test_apply_critic_weakens_ghost_to_unresolved():
    """WEAKENED on a GHOST → UNRESOLVED, citation cleared."""
    output = _output_with_ghosts(
        [{"id": "t1", "citation": "src/auth.py:5", "note": "handled"}]
    )
    crit = CriticResult(
        finding_id="t1",
        status="WEAKENED",
        issues=["cited mitigation only covers happy path"],
        counterevidence=[],
        recommended_label=None,
    )
    new_output = apply_critic_results(output, [crit])
    new_finding = next(c for c in new_output.classifications if c.id == "t1")
    assert new_finding.label == "UNRESOLVED"
    assert new_finding.citation is None


def test_apply_critic_confirms_ghost():
    """CONFIRMED on a GHOST → no change."""
    original = _output_with_ghosts(
        [{"id": "t1", "citation": "src/auth.py:5", "note": "handled"}]
    )
    crit = CriticResult(
        finding_id="t1",
        status="CONFIRMED",
        issues=[],
        counterevidence=[],
        recommended_label=None,
    )
    new_output = apply_critic_results(original, [crit])
    new_finding = next(c for c in new_output.classifications if c.id == "t1")
    assert new_finding.label == "GHOST"
    assert new_finding.citation == "src/auth.py:5"


# ---------------------------------------------------------------------------
# CLI flag exposure.
# ---------------------------------------------------------------------------


def test_cli_help_lists_critic_ghosts_flag():
    """Inspect the click command's registered options directly so the
    assertion is independent of terminal width / Typer's rich help
    wrapping (CI runners sometimes wrap long flags onto two lines)."""
    from typer.main import get_command
    from antemortem.cli import app

    run_cmd = get_command(app).get_command(None, "run")
    flags = {opt for param in run_cmd.params for opt in getattr(param, "opts", [])}
    assert "--critic-ghosts" in flags


def test_cli_run_rejects_unknown_critic_ghosts_mode(tmp_path, monkeypatch):
    """Misspelling (--critic-ghosts huh) exits 2 with a helpful error,
    not a confusing later failure."""
    from typer.testing import CliRunner
    from unittest.mock import MagicMock, patch
    from antemortem.cli import app

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text("\n".join(f"l{i}" for i in range(20)), encoding="utf-8")

    doc = tmp_path / "feat.md"
    doc.write_text(
        "---\nname: feat\ndate: 2026-04-21\ntemplate: basic\n---\n\n"
        "# x\n\n## 1. The change\n\nx.\n\n"
        "## 2. Traps hypothesized\n\n"
        "| # | trap | label | P(issue) | notes |\n"
        "|---|------|-------|----------|-------|\n"
        "| 1 | x | trap | 60% | n |\n\n"
        "## 3. Recon protocol\n\n"
        "- **Files handed to the model:**\n"
        "  - `src/auth.py`\n",
        encoding="utf-8",
    )

    fake = MagicMock()
    fake.structured_complete.return_value = (
        AntemortemOutput(
            classifications=[
                Classification(id="t1", label="GHOST", citation="src/auth.py:5", note="x"),
            ],
        ),
        {
            "input_tokens": 10, "output_tokens": 20,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        },
    )
    fake.name = "anthropic"
    fake.model = "mock"
    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = CliRunner().invoke(
            app, ["run", str(doc), "--repo", str(repo), "--critic-ghosts", "huh"],
        )
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# MCP signature exposes critic_ghosts.
# ---------------------------------------------------------------------------


def test_mcp_run_schema_exposes_critic_ghosts():
    import asyncio
    from antemortem.mcp import mcp_app

    tools = asyncio.run(mcp_app.list_tools())
    run = next(t for t in tools if t.name == "run")
    assert "critic_ghosts" in run.inputSchema["properties"]
