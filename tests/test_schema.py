"""Schema validation tests — confirm the Pydantic contract is strict where it matters."""

import pytest
from pydantic import ValidationError

from antemortem.schema import (
    AntemortemDocument,
    AntemortemOutput,
    Classification,
    Frontmatter,
    NewTrap,
    Trap,
)


def test_frontmatter_required_fields():
    fm = Frontmatter(name="feat", date="2026-04-21")
    assert fm.name == "feat"
    assert fm.status == "draft"
    assert fm.template == "basic"


def test_frontmatter_rejects_missing_name():
    with pytest.raises(ValidationError):
        Frontmatter(date="2026-04-21")


def test_classification_accepts_all_labels():
    for label in ("REAL", "GHOST", "NEW", "UNRESOLVED"):
        c = Classification(id="t1", label=label, citation="foo.py:1", note="x")
        assert c.label == label


def test_classification_rejects_invalid_label():
    with pytest.raises(ValidationError):
        Classification(id="t1", label="MAYBE", citation=None, note="")


def test_classification_citation_can_be_none_for_unresolved():
    c = Classification(id="t1", label="UNRESOLVED", citation=None, note="no evidence")
    assert c.citation is None


def test_new_trap_id_pattern_enforced():
    # valid
    NewTrap(id="t_new_1", hypothesis="x", citation="foo.py:1", note="")
    NewTrap(id="t_new_42", hypothesis="x", citation="foo.py:1", note="")
    # invalid
    with pytest.raises(ValidationError):
        NewTrap(id="t1", hypothesis="x", citation="foo.py:1", note="")
    with pytest.raises(ValidationError):
        NewTrap(id="new_1", hypothesis="x", citation="foo.py:1", note="")


def test_antemortem_output_defaults_empty_lists():
    out = AntemortemOutput()
    assert out.classifications == []
    assert out.new_traps == []
    assert out.spec_mutations == []


def test_antemortem_output_roundtrips_json():
    out = AntemortemOutput(
        classifications=[Classification(id="t1", label="REAL", citation="a.py:10", note="n")],
        new_traps=[NewTrap(id="t_new_1", hypothesis="h", citation="b.py:5", note="")],
        spec_mutations=["add X"],
    )
    payload = out.model_dump_json()
    restored = AntemortemOutput.model_validate_json(payload)
    assert restored == out


def test_antemortem_document_constructs():
    doc = AntemortemDocument(
        frontmatter=Frontmatter(name="feat", date="2026-04-21"),
        spec="one paragraph",
        files_to_read=["src/foo.py"],
        traps=[Trap(id="t1", hypothesis="risk", type="trap")],
        raw_markdown="...",
    )
    assert doc.frontmatter.name == "feat"
    assert len(doc.traps) == 1
