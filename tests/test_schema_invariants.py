# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Reviewer P0: Pydantic schema enforces citation/label invariant.

Pre-fix the contract \"UNRESOLVED requires citation=None, others require
a citation\" lived only in ``lint``. A provider could return
``label=GHOST`` with ``citation=None`` and Pydantic accepted it; the
decision gate would build on a structurally-invalid finding.

Post-fix:
- Classification.model_validator rejects mismatches at parse time.
- NewTrap.citation has min_length=1 (no empty strings).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from antemortem.schema import AntemortemOutput, Classification, NewTrap


# ---------------------------------------------------------------------------
# Classification.
# ---------------------------------------------------------------------------


def test_unresolved_with_citation_rejected():
    """An UNRESOLVED finding with a citation is structurally invalid —
    if there's evidence, the label should be REAL/GHOST/NEW."""
    with pytest.raises(ValidationError, match="UNRESOLVED must have"):
        Classification(
            id="t1", label="UNRESOLVED", citation="src/auth.py:5", note="x",
        )


def test_real_without_citation_rejected():
    with pytest.raises(ValidationError, match="REAL requires"):
        Classification(id="t1", label="REAL", citation=None, note="x")


def test_ghost_without_citation_rejected():
    with pytest.raises(ValidationError, match="GHOST requires"):
        Classification(id="t1", label="GHOST", citation=None, note="x")


def test_new_label_classification_without_citation_rejected():
    """Classification.label can be NEW too (the user-trap classification
    of a previously unknown trap). NEW also requires citation."""
    with pytest.raises(ValidationError, match="NEW requires"):
        Classification(id="t1", label="NEW", citation=None, note="x")


def test_real_with_empty_string_citation_rejected():
    """Empty string is no better than None for citation — both mean
    'no evidence'. Don't let the LLM slip an empty string through."""
    with pytest.raises(ValidationError, match="requires"):
        Classification(id="t1", label="REAL", citation="", note="x")


@pytest.mark.parametrize("label", ["REAL", "GHOST", "NEW"])
def test_non_unresolved_with_valid_citation_accepted(label):
    c = Classification(id="t1", label=label, citation="src/auth.py:5", note="x")
    assert c.label == label
    assert c.citation == "src/auth.py:5"


def test_unresolved_with_null_citation_accepted():
    c = Classification(id="t1", label="UNRESOLVED", citation=None, note="x")
    assert c.label == "UNRESOLVED"
    assert c.citation is None


# ---------------------------------------------------------------------------
# NewTrap.
# ---------------------------------------------------------------------------


def test_new_trap_requires_citation():
    """NewTrap.citation is required by the type system AND non-empty."""
    with pytest.raises(ValidationError):
        NewTrap(id="t_new_1", hypothesis="x")  # type: ignore[call-arg]


def test_new_trap_empty_citation_rejected():
    with pytest.raises(ValidationError, match="at least 1"):
        NewTrap(id="t_new_1", hypothesis="x", citation="")


def test_new_trap_with_citation_accepted():
    nt = NewTrap(id="t_new_1", hypothesis="x", citation="src/auth.py:5")
    assert nt.citation == "src/auth.py:5"
    assert nt.label == "NEW"  # Literal["NEW"] default


# ---------------------------------------------------------------------------
# AntemortemOutput round-trip after invariants.
# ---------------------------------------------------------------------------


def test_antemortem_output_validates_each_classification():
    """The model_validator runs on every nested Classification when
    constructing the output — bad nested entries fail upfront."""
    with pytest.raises(ValidationError):
        AntemortemOutput(
            classifications=[
                Classification(id="t1", label="REAL", citation="src/a.py:1", note=""),
                # Second one violates the invariant:
                Classification(id="t2", label="UNRESOLVED", citation="src/b.py:1", note=""),
            ],
        )


def test_antemortem_output_round_trip_json_preserves_invariant():
    """An invalid finding can't slip in via model_validate_json either."""
    bad = (
        '{"classifications": ['
        '  {"id": "t1", "label": "REAL", "citation": null, "note": ""}'
        ']}'
    )
    with pytest.raises(ValidationError):
        AntemortemOutput.model_validate_json(bad)
