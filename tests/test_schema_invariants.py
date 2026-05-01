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


# ---------------------------------------------------------------------------
# Runtime path: LLM returning an invalid classification surfaces a
# readable error to the user, not a stack trace.
# ---------------------------------------------------------------------------


def test_llm_returning_invalid_classification_raises_readable_error(tmp_path, monkeypatch):
    """When a provider's structured_complete tries to construct a
    Classification(label=GHOST, citation=None), the model_validator
    raises ValidationError. The user-facing CLI must surface a clean
    message, not a stack trace.

    The test simulates the provider failing at construction time by
    making the mock provider itself raise the same ValidationError the
    real Pydantic path would raise.
    """
    from typer.testing import CliRunner
    from unittest.mock import MagicMock, patch
    from antemortem.cli import app

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    runner = CliRunner()

    # Build a real ValidationError the way Pydantic would on the
    # invariant violation:
    try:
        Classification(id="t1", label="GHOST", citation=None, note="x")
    except ValidationError as exc:
        invariant_error = exc
    else:
        raise AssertionError("Expected schema invariant to raise")

    # Provider raises ValidationError at structured_complete time —
    # i.e. the LLM response failed schema validation. Match what a
    # real provider would do: re-raise as ProviderError so the CLI's
    # except ProviderError block catches it.
    from antemortem.providers.base import ProviderError

    fake = MagicMock()
    fake.name = "anthropic"
    fake.model = "mock"
    fake.structured_complete.side_effect = ProviderError(
        f"LLM returned schema-invalid output: {invariant_error}"
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text("\n".join(f"l{i}" for i in range(20)), encoding="utf-8")
    doc = tmp_path / "feat.md"
    doc.write_text(
        "---\nname: feat\ndate: 2026-04-21\ntemplate: basic\n---\n\n"
        "# Antemortem — feat\n\n## 1. The change\n\nx.\n\n"
        "## 2. Traps hypothesized\n\n"
        "| # | trap | label | P(issue) | notes |\n"
        "|---|------|-------|----------|-------|\n"
        "| 1 | x | trap | 60% | n |\n\n"
        "## 3. Recon protocol\n\n"
        "- **Files handed to the model:**\n"
        "  - `src/auth.py`\n",
        encoding="utf-8",
    )

    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc), "--repo", str(repo)])

    # Should exit cleanly with non-zero, with a user-readable message —
    # NOT an unhandled exception that prints a Python stack trace.
    assert result.exit_code != 0
    output = (result.stdout or "") + (result.stderr or "") + str(result.exception or "")
    assert "schema" in output.lower() or "validation" in output.lower() or "Classification" in output
    # No "Traceback" should leak to the user (Click's runner catches it
    # but might re-render — check the rendered text):
    rendered = result.output if hasattr(result, "output") else result.stdout
    assert "Traceback" not in (rendered or "")
