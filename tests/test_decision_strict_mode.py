# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Reviewer P1: SAFE_TO_PROCEED label + strict-unresolved policy.

Pre-fix the gate could land on SAFE_TO_PROCEED with one UNRESOLVED
finding because the ratio rule fires only when unresolved/total >= 0.5
AND unresolved >= 2. Defensible, but external users read SAFE as
\"risk-free\".

Post-fix:
- ``DecisionPolicy(unresolved_policy=\"any_blocks_safe\")`` flips ANY
  UNRESOLVED to NEEDS_MORE_EVIDENCE.
- The default rationale now explicitly says SAFE means \"no blocker
  in the supplied files\", not \"risk-free\".

CLI ``--strict-unresolved`` and MCP ``strict_unresolved=True`` enable
the policy.
"""
from __future__ import annotations

from antemortem.decision import (
    DecisionPolicy,
    compute_decision,
)
from antemortem.schema import AntemortemOutput, Classification


def _output(*labels_and_citations) -> AntemortemOutput:
    cls = []
    for i, (label, cite) in enumerate(labels_and_citations, start=1):
        cls.append(
            Classification(
                id=f"t{i}", label=label,
                citation=cite, note="x",
            )
        )
    return AntemortemOutput(classifications=cls)


# ---------------------------------------------------------------------------
# Default policy ('ratio') — preserves pre-v0.7 behaviour.
# ---------------------------------------------------------------------------


def test_default_policy_safe_with_one_unresolved_among_many():
    output = _output(
        ("GHOST", "src/a.py:1"),
        ("GHOST", "src/a.py:2"),
        ("GHOST", "src/a.py:3"),
        ("UNRESOLVED", None),
    )
    decision = compute_decision(output)
    assert decision.decision == "SAFE_TO_PROCEED"


def test_default_policy_needs_more_evidence_when_half_unresolved():
    output = _output(
        ("GHOST", "src/a.py:1"),
        ("UNRESOLVED", None),
        ("UNRESOLVED", None),
    )
    decision = compute_decision(output)
    assert decision.decision == "NEEDS_MORE_EVIDENCE"


# ---------------------------------------------------------------------------
# Strict policy — ANY UNRESOLVED prevents SAFE_TO_PROCEED.
# ---------------------------------------------------------------------------


def test_strict_policy_any_unresolved_prevents_safe():
    output = _output(
        ("GHOST", "src/a.py:1"),
        ("GHOST", "src/a.py:2"),
        ("GHOST", "src/a.py:3"),
        ("UNRESOLVED", None),  # only one — default ratio path would say SAFE
    )
    strict = DecisionPolicy(unresolved_policy="any_blocks_safe")
    decision = compute_decision(output, policy=strict)
    assert decision.decision == "NEEDS_MORE_EVIDENCE"
    assert "strict policy" in decision.rationale or "any_blocks_safe" in decision.rationale


def test_strict_policy_safe_when_zero_unresolved():
    output = _output(
        ("GHOST", "src/a.py:1"),
        ("GHOST", "src/a.py:2"),
    )
    strict = DecisionPolicy(unresolved_policy="any_blocks_safe")
    decision = compute_decision(output, policy=strict)
    assert decision.decision == "SAFE_TO_PROCEED"


def test_strict_policy_does_not_override_do_not_proceed():
    """A high-severity unmitigated REAL still fails outright; the
    strict policy doesn't downgrade DO_NOT_PROCEED to NEEDS_MORE_EVIDENCE."""
    output = AntemortemOutput(
        classifications=[
            Classification(
                id="t1", label="REAL", citation="src/a.py:1",
                note="x", severity="high",
                # no remediation
            ),
            Classification(
                id="t2", label="UNRESOLVED", citation=None, note="x",
            ),
        ],
    )
    strict = DecisionPolicy(unresolved_policy="any_blocks_safe")
    decision = compute_decision(output, policy=strict)
    assert decision.decision == "DO_NOT_PROCEED"


# ---------------------------------------------------------------------------
# Default rationale tightens the SAFE language.
# ---------------------------------------------------------------------------


def test_safe_rationale_does_not_claim_risk_free():
    output = _output(
        ("GHOST", "src/a.py:1"),
        ("GHOST", "src/a.py:2"),
    )
    decision = compute_decision(output)
    assert decision.decision == "SAFE_TO_PROCEED"
    rationale = decision.rationale.lower()
    # Should hedge: "no blocker in supplied files", "not a proof" — not
    # claim absolute risk absence.
    assert "no blocker" in rationale or "not a proof" in rationale
    # The phrase "risk-free" only appears in the negation
    # ("not a proof that the change is risk-free"), never as a positive
    # claim.
    if "risk-free" in rationale:
        assert "not" in rationale.split("risk-free")[0][-100:].lower(), (
            "rationale claims 'risk-free' without negation"
        )


# ---------------------------------------------------------------------------
# CLI flag.
# ---------------------------------------------------------------------------


def test_cli_help_lists_strict_unresolved_flag():
    from typer.testing import CliRunner
    from antemortem.cli import app

    result = CliRunner().invoke(app, ["run", "--help"], env={"COLUMNS": "200"})
    assert "--strict-unresolved" in result.stdout


def test_mcp_run_schema_exposes_strict_unresolved():
    import asyncio
    from antemortem.mcp import mcp_app

    tools = asyncio.run(mcp_app.list_tools())
    run = next(t for t in tools if t.name == "run")
    assert "strict_unresolved" in run.inputSchema["properties"]
