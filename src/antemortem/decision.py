# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Four-level decision gate for antemortem outputs.

After the classifier pass (and optionally the critic pass), the CLI
computes one of:

- ``SAFE_TO_PROCEED`` ??no blocking REAL findings, UNRESOLVED count is
  low, hard-gate pass rate is perfect.
- ``PROCEED_WITH_GUARDS`` ??REAL findings exist but each has a
  remediation suggestion, and nothing high-severity is unmitigated.
- ``NEEDS_MORE_EVIDENCE`` ??UNRESOLVED count is non-trivial relative to
  the total finding count. The antemortem needs more files before it
  can ship a verdict.
- ``DO_NOT_PROCEED`` ??at least one high-severity REAL finding without a
  remediation, OR a CONTRADICTED finding the critic flagged as
  structurally unsafe.

The rules are intentionally conservative ??we optimize for low
false-positive "safe" verdicts at the cost of occasional
"proceed-with-guards" on cases that would have been fine. Downstream CI
can override by ignoring specific decision levels.
"""

from __future__ import annotations

from dataclasses import dataclass

from antemortem.schema import AntemortemOutput


DECISION_LABELS = (
    "SAFE_TO_PROCEED",
    "PROCEED_WITH_GUARDS",
    "NEEDS_MORE_EVIDENCE",
    "DO_NOT_PROCEED",
)


@dataclass(frozen=True)
class DecisionReport:
    """Computed decision plus the counts that produced it."""

    decision: str
    rationale: str
    counts: dict[str, int]


def compute_decision(output: AntemortemOutput) -> DecisionReport:
    """Decide the four-level verdict from an ``AntemortemOutput``.

    Input is the *final* output ??post-critic if the critic pass ran.
    The decision considers:

    - label counts (REAL / GHOST / NEW / UNRESOLVED)
    - severity (when the model provided it; defaults to medium otherwise)
    - remediation presence on REAL / NEW findings
    - critic-flagged contradictions

    No rule uses confidence directly ??confidence is informational for
    the reader, not a gate input, because uncalibrated model self-
    confidence is known to be unreliable as a safety signal.
    """
    counts = _count_labels(output)
    reals = _reals(output)
    unresolved = counts.get("UNRESOLVED", 0)
    total = sum(counts.values()) or 1

    high_real_unmitigated = [
        f for f in reals if _severity(f) == "high" and not _remediation(f)
    ]
    if high_real_unmitigated:
        names = ", ".join(f["id"] for f in high_real_unmitigated)
        return DecisionReport(
            decision="DO_NOT_PROCEED",
            rationale=(
                f"Found {len(high_real_unmitigated)} high-severity REAL "
                f"finding(s) with no remediation: {names}. The change cannot "
                "ship until each has a concrete mitigation or is downgraded."
            ),
            counts=counts,
        )

    if _has_strong_contradiction(output):
        return DecisionReport(
            decision="DO_NOT_PROCEED",
            rationale=(
                "The critic flagged a CONTRADICTED finding with counterevidence "
                "that suggests a structurally unsafe assumption in the spec. "
                "Revise the spec before proceeding."
            ),
            counts=counts,
        )

    if unresolved / total >= 0.5 and unresolved >= 2:
        return DecisionReport(
            decision="NEEDS_MORE_EVIDENCE",
            rationale=(
                f"{unresolved} of {total} findings are UNRESOLVED. Add more "
                "files to the Recon protocol section and re-run before deciding."
            ),
            counts=counts,
        )

    if reals:
        unmitigated = [f for f in reals if not _remediation(f)]
        if unmitigated:
            names = ", ".join(f["id"] for f in unmitigated)
            return DecisionReport(
                decision="NEEDS_MORE_EVIDENCE",
                rationale=(
                    f"{len(unmitigated)} REAL finding(s) without remediation: "
                    f"{names}. Add mitigations (or downgrade via evidence) "
                    "before marking the plan shippable."
                ),
                counts=counts,
            )
        return DecisionReport(
            decision="PROCEED_WITH_GUARDS",
            rationale=(
                f"{len(reals)} REAL finding(s), each with a remediation. "
                "Implementation can proceed if the remediations are applied."
            ),
            counts=counts,
        )

    return DecisionReport(
        decision="SAFE_TO_PROCEED",
        rationale=(
            f"No REAL findings. {counts.get('GHOST', 0)} GHOST / "
            f"{unresolved} UNRESOLVED. The antemortem surfaced no blocker; "
            "the plan is shippable as-is."
        ),
        counts=counts,
    )


# ---------------------------- internals ----------------------------


def _count_labels(output: AntemortemOutput) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in output.classifications:
        counts[c.label] = counts.get(c.label, 0) + 1
    # NEW traps are also findings; count them under NEW.
    for _ in output.new_traps:
        counts["NEW"] = counts.get("NEW", 0) + 1
    return counts


def _reals(output: AntemortemOutput) -> list[dict]:
    """Return a flat list of REAL / NEW findings as plain dicts.

    Unified dict shape makes the rule code simpler below.
    """
    out: list[dict] = []
    for c in output.classifications:
        if c.label in ("REAL", "NEW"):
            out.append(
                {
                    "id": c.id,
                    "label": c.label,
                    "severity": c.severity,
                    "remediation": c.remediation,
                }
            )
    for nt in output.new_traps:
        out.append(
            {
                "id": nt.id,
                "label": "NEW",
                "severity": nt.severity,
                "remediation": nt.remediation,
            }
        )
    return out


def _severity(finding: dict) -> str:
    return finding.get("severity") or "medium"


def _remediation(finding: dict) -> str | None:
    r = finding.get("remediation")
    return r if r and r.strip() else None


def _has_strong_contradiction(output: AntemortemOutput) -> bool:
    """True if the critic pass produced a CONTRADICTED with counterevidence."""
    for c in output.critic_results or []:
        if c.status == "CONTRADICTED" and c.counterevidence:
            return True
    return False
