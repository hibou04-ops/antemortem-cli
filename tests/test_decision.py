"""Four-level decision gate tests - deterministic, no model calls."""

from __future__ import annotations

from antemortem.decision import compute_decision
from antemortem.schema import (
    AntemortemOutput,
    Classification,
    CriticResult,
    NewTrap,
)


def _output(
    classifications: list[Classification] | None = None,
    new_traps: list[NewTrap] | None = None,
    critic_results: list[CriticResult] | None = None,
) -> AntemortemOutput:
    return AntemortemOutput(
        classifications=classifications or [],
        new_traps=new_traps or [],
        critic_results=critic_results or [],
    )


# ---- SAFE_TO_PROCEED ----


def test_safe_to_proceed_all_ghost():
    out = _output(
        classifications=[
            Classification(id="t1", label="GHOST", citation="a:1", note="n"),
            Classification(id="t2", label="GHOST", citation="a:2", note="n"),
        ]
    )
    report = compute_decision(out)
    assert report.decision == "SAFE_TO_PROCEED"
    assert "No REAL findings" in report.rationale


def test_safe_to_proceed_empty():
    out = _output()
    report = compute_decision(out)
    assert report.decision == "SAFE_TO_PROCEED"


def test_safe_to_proceed_ghost_and_unresolved_no_real():
    out = _output(
        classifications=[
            Classification(id="t1", label="GHOST", citation="a:1", note=""),
            Classification(id="t2", label="UNRESOLVED", citation=None, note=""),
        ]
    )
    report = compute_decision(out)
    assert report.decision == "SAFE_TO_PROCEED"


# ---- PROCEED_WITH_GUARDS ----


def test_proceed_with_guards_real_with_remediation():
    out = _output(
        classifications=[
            Classification(
                id="t1",
                label="REAL",
                citation="a:1",
                note="real issue",
                remediation="Add retry with backoff.",
                severity="medium",
            )
        ]
    )
    report = compute_decision(out)
    assert report.decision == "PROCEED_WITH_GUARDS"
    assert "remediation" in report.rationale


def test_proceed_with_guards_multiple_reals_all_remediated():
    out = _output(
        classifications=[
            Classification(
                id=f"t{i}",
                label="REAL",
                citation=f"a:{i}",
                note="",
                remediation="mitigation",
                severity="low",
            )
            for i in range(1, 4)
        ]
    )
    report = compute_decision(out)
    assert report.decision == "PROCEED_WITH_GUARDS"


# ---- NEEDS_MORE_EVIDENCE ----


def test_needs_more_evidence_real_without_remediation():
    out = _output(
        classifications=[
            Classification(
                id="t1",
                label="REAL",
                citation="a:1",
                note="",
                severity="medium",
                # no remediation
            )
        ]
    )
    report = compute_decision(out)
    assert report.decision == "NEEDS_MORE_EVIDENCE"
    assert "without remediation" in report.rationale


def test_needs_more_evidence_high_unresolved_ratio():
    # 3 UNRESOLVED out of 4 total (75%) and count >= 2
    out = _output(
        classifications=[
            Classification(id="t1", label="GHOST", citation="a:1", note=""),
            Classification(id="t2", label="UNRESOLVED", citation=None, note=""),
            Classification(id="t3", label="UNRESOLVED", citation=None, note=""),
            Classification(id="t4", label="UNRESOLVED", citation=None, note=""),
        ]
    )
    report = compute_decision(out)
    assert report.decision == "NEEDS_MORE_EVIDENCE"
    assert "UNRESOLVED" in report.rationale


def test_needs_more_evidence_ignores_single_unresolved():
    # Only 1 UNRESOLVED — threshold requires >= 2
    out = _output(
        classifications=[
            Classification(id="t1", label="GHOST", citation="a:1", note=""),
            Classification(id="t2", label="UNRESOLVED", citation=None, note=""),
        ]
    )
    report = compute_decision(out)
    assert report.decision == "SAFE_TO_PROCEED"


# ---- DO_NOT_PROCEED ----


def test_do_not_proceed_high_severity_real_without_remediation():
    out = _output(
        classifications=[
            Classification(
                id="t1",
                label="REAL",
                citation="a:1",
                note="critical issue",
                severity="high",
                # no remediation
            )
        ]
    )
    report = compute_decision(out)
    assert report.decision == "DO_NOT_PROCEED"
    assert "high-severity" in report.rationale


def test_do_not_proceed_on_strong_contradiction():
    out = _output(
        classifications=[
            Classification(id="t1", label="REAL", citation="a:1", note=""),
        ],
        critic_results=[
            CriticResult(
                finding_id="t1",
                status="CONTRADICTED",
                issues=["structural issue"],
                counterevidence=["b:10"],
            )
        ],
    )
    report = compute_decision(out)
    assert report.decision == "DO_NOT_PROCEED"
    assert "CONTRADICTED" in report.rationale


def test_contradiction_without_counterevidence_does_not_block():
    # Status CONTRADICTED but no counterevidence — not strong enough to block
    out = _output(
        classifications=[
            Classification(
                id="t1",
                label="REAL",
                citation="a:1",
                note="",
                remediation="fix",
                severity="medium",
            )
        ],
        critic_results=[
            CriticResult(
                finding_id="t1",
                status="CONTRADICTED",
                issues=["ambiguous"],
                counterevidence=[],  # empty
            )
        ],
    )
    report = compute_decision(out)
    # Not DO_NOT_PROCEED - falls to PROCEED_WITH_GUARDS because REAL has remediation
    assert report.decision == "PROCEED_WITH_GUARDS"


def test_high_severity_with_remediation_proceeds_with_guards():
    out = _output(
        classifications=[
            Classification(
                id="t1",
                label="REAL",
                citation="a:1",
                note="",
                severity="high",
                remediation="Apply mitigation X.",
            )
        ]
    )
    report = compute_decision(out)
    # High severity + has remediation -> proceed with guards, not blocked
    assert report.decision == "PROCEED_WITH_GUARDS"


# ---- counts populated ----


def test_counts_reflect_labels():
    out = _output(
        classifications=[
            Classification(id="t1", label="REAL", citation="a:1", note="",
                           remediation="x", severity="low"),
            Classification(id="t2", label="GHOST", citation="a:2", note=""),
            Classification(id="t3", label="UNRESOLVED", citation=None, note=""),
        ],
        new_traps=[
            NewTrap(id="t_new_1", hypothesis="h", citation="a:4", note=""),
        ],
    )
    report = compute_decision(out)
    assert report.counts.get("REAL") == 1
    assert report.counts.get("GHOST") == 1
    assert report.counts.get("UNRESOLVED") == 1
    assert report.counts.get("NEW") == 1
