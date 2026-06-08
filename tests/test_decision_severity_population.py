# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Severity-population guard for the decision gate (deterministic, no network).

A REAL / NEW finding whose ``severity`` field is OMITTED used to default
to ``"medium"`` (``_severity`` in ``decision.py``). That let an
unmitigated finding with no stated severity slip past:

  1. the in-process high-severity block (``_severity(f) == "high"``), and
  2. the CI ``high_severity_block_rate=1.0`` floor (eval's high-sev
     detector likewise keys off severity).

These tests pin the fail-safe contract: a MISSING severity reads as
``"high"`` so the unmitigated finding BLOCKS rather than degrades to a
softer verdict. Explicit ``low`` / ``medium`` / ``high`` are honoured
unchanged.
"""

from __future__ import annotations

from antemortem.decision import _severity, compute_decision
from antemortem.commands.eval import _has_high_severity_unmitigated_finding
from antemortem.schema import AntemortemOutput, Classification, NewTrap


def _output(
    classifications: list[Classification] | None = None,
    new_traps: list[NewTrap] | None = None,
) -> AntemortemOutput:
    return AntemortemOutput(
        classifications=classifications or [],
        new_traps=new_traps or [],
        critic_results=[],
    )


# ---- the helper itself ----


def test_severity_missing_reads_as_high():
    # Both an absent key and an explicit None must fail safe to "high".
    assert _severity({}) == "high"
    assert _severity({"severity": None}) == "high"


def test_severity_empty_string_reads_as_high():
    # An empty / whitespace severity is "absent" for gate purposes.
    assert _severity({"severity": ""}) == "high"


def test_severity_explicit_values_are_honoured():
    assert _severity({"severity": "low"}) == "low"
    assert _severity({"severity": "medium"}) == "medium"
    assert _severity({"severity": "high"}) == "high"


# ---- end-to-end through compute_decision ----


def test_missing_severity_unmitigated_real_blocks():
    # REAL finding, no remediation, severity omitted -> must DO_NOT_PROCEED,
    # NOT the pre-fix NEEDS_MORE_EVIDENCE (which "medium" produced).
    out = _output(
        classifications=[
            Classification(
                id="t1",
                label="REAL",
                citation="a:1",
                note="no severity stated",
                # severity omitted, no remediation
            )
        ]
    )
    report = compute_decision(out)
    assert report.decision == "DO_NOT_PROCEED"
    assert "high-severity" in report.rationale
    assert "t1" in report.rationale


def test_eval_high_sev_detector_mirrors_the_gate_on_omitted_severity():
    # The CI high_severity_block_rate floor relies on eval's high-sev DETECTOR
    # counting the SAME findings the live gate blocks. The detector is now a
    # faithful mirror of compute_decision's high_real_unmitigated set (via
    # _reals + _severity + _remediation), so an omitted-severity unmitigated
    # REAL finding is counted (not vacuously skipped) AND the gate blocks it --
    # the two must agree, or the floor passes without measuring the evasion.
    out = _output(
        classifications=[
            Classification(
                id="t1",
                label="REAL",
                citation="a:1",
                note="no severity stated",
                # severity omitted, no remediation
            )
        ]
    )
    assert _has_high_severity_unmitigated_finding(out) is True
    assert compute_decision(out).decision == "DO_NOT_PROCEED"


def test_missing_severity_unmitigated_new_trap_blocks():
    out = _output(
        new_traps=[
            NewTrap(
                id="t_new_1",
                hypothesis="model-surfaced risk",
                citation="a:1",
                note="",
                # severity omitted, no remediation
            )
        ]
    )
    report = compute_decision(out)
    assert report.decision == "DO_NOT_PROCEED"
    assert "high-severity" in report.rationale


def test_missing_severity_with_remediation_does_not_block():
    # Fail-safe only bites the UNMITIGATED case. A missing-severity REAL
    # that DOES carry a remediation still flows to PROCEED_WITH_GUARDS
    # (the high-sev block is gated on "no remediation").
    out = _output(
        classifications=[
            Classification(
                id="t1",
                label="REAL",
                citation="a:1",
                note="",
                remediation="Add a bounds check before the cast.",
                # severity omitted
            )
        ]
    )
    report = compute_decision(out)
    assert report.decision == "PROCEED_WITH_GUARDS"


def test_explicit_low_severity_unmitigated_does_not_block():
    # Regression guard: an EXPLICIT low/medium severity must NOT be
    # promoted to high. It still falls to NEEDS_MORE_EVIDENCE (REAL with
    # no remediation), never DO_NOT_PROCEED.
    out = _output(
        classifications=[
            Classification(
                id="t1",
                label="REAL",
                citation="a:1",
                note="",
                severity="low",
                # no remediation
            )
        ]
    )
    report = compute_decision(out)
    assert report.decision == "NEEDS_MORE_EVIDENCE"
    assert "without remediation" in report.rationale
