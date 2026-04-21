"""Critic pass tests - mocked provider, deterministic policy checks."""

from __future__ import annotations

from unittest.mock import MagicMock

from antemortem.critic import apply_critic_results, build_critic_payload, run_critic_pass
from antemortem.schema import (
    AntemortemOutput,
    Classification,
    CriticResult,
    NewTrap,
)


def _output_with(
    classifications: list[Classification] | None = None,
    new_traps: list[NewTrap] | None = None,
) -> AntemortemOutput:
    return AntemortemOutput(
        classifications=classifications or [],
        new_traps=new_traps or [],
    )


# ---- build_critic_payload ----


def test_build_critic_payload_contains_all_blocks():
    out = _output_with(
        classifications=[
            Classification(id="t1", label="REAL", citation="foo.py:10", note="n"),
        ]
    )
    payload = build_critic_payload(
        spec="spec text",
        traps_table_md="| id | hypothesis | type |",
        files=[("a.py", "line1\nline2\n")],
        first_pass=out,
    )
    assert "<files>" in payload
    assert "<spec>" in payload
    assert "<traps>" in payload
    assert "<first_pass>" in payload
    assert "id=t1" in payload
    assert "label=REAL" in payload


def test_build_critic_payload_no_findings():
    out = _output_with()
    payload = build_critic_payload(
        spec="x",
        traps_table_md="| id | hypothesis | type |",
        files=[("a.py", "z\n")],
        first_pass=out,
    )
    assert "(none)" in payload


# ---- run_critic_pass delegates to provider ----


def test_run_critic_pass_uses_critic_prompt_and_schema():
    provider = MagicMock()
    provider.name = "mock"
    provider.model = "m"
    # The critic returns an AntemortemOutput with only critic_results populated.
    empty_with_critics = AntemortemOutput(
        critic_results=[
            CriticResult(
                finding_id="t1",
                status="CONFIRMED",
                issues=[],
                counterevidence=[],
                recommended_label=None,
            )
        ]
    )
    provider.structured_complete.return_value = (
        empty_with_critics,
        {"input_tokens": 100, "output_tokens": 50,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    )

    out = _output_with(
        classifications=[
            Classification(id="t1", label="REAL", citation="foo.py:1", note="n"),
        ]
    )
    results, usage = run_critic_pass(
        provider,
        spec="s",
        traps_table_md="| id | hypothesis | type |",
        files=[("foo.py", "line\n")],
        first_pass=out,
    )

    assert len(results) == 1
    assert results[0].status == "CONFIRMED"
    kw = provider.structured_complete.call_args.kwargs
    from antemortem.prompts import CRITIC_SYSTEM_PROMPT

    assert kw["system_prompt"] == CRITIC_SYSTEM_PROMPT
    assert "<first_pass>" in kw["user_content"]


# ---- apply_critic_results policy ----


def test_confirmed_leaves_classification_unchanged():
    cls = Classification(id="t1", label="REAL", citation="foo.py:5", note="original")
    out = _output_with(classifications=[cls])
    crit = CriticResult(finding_id="t1", status="CONFIRMED")
    result = apply_critic_results(out, [crit])
    assert len(result.classifications) == 1
    assert result.classifications[0].label == "REAL"
    assert result.classifications[0].citation == "foo.py:5"
    assert result.classifications[0].note == "original"
    assert len(result.critic_results) == 1


def test_weakened_downgrades_classification_to_unresolved_clears_citation():
    cls = Classification(id="t1", label="REAL", citation="foo.py:5", note="original")
    out = _output_with(classifications=[cls])
    crit = CriticResult(
        finding_id="t1",
        status="WEAKENED",
        issues=["weak causal path"],
    )
    result = apply_critic_results(out, [crit])
    assert result.classifications[0].label == "UNRESOLVED"
    assert result.classifications[0].citation is None
    assert "weak causal path" in result.classifications[0].note
    assert "original" in result.classifications[0].note


def test_contradicted_with_recommended_label_flips_to_that_label():
    cls = Classification(id="t1", label="REAL", citation="foo.py:5", note="n")
    out = _output_with(classifications=[cls])
    crit = CriticResult(
        finding_id="t1",
        status="CONTRADICTED",
        issues=["mitigation visible"],
        counterevidence=["bar.py:20"],
        recommended_label="GHOST",
    )
    result = apply_critic_results(out, [crit])
    assert result.classifications[0].label == "GHOST"
    # GHOST keeps the original citation by policy
    assert result.classifications[0].citation == "foo.py:5"
    assert "bar.py:20" in result.classifications[0].note


def test_contradicted_without_recommended_label_goes_to_unresolved():
    cls = Classification(id="t1", label="REAL", citation="foo.py:5", note="n")
    out = _output_with(classifications=[cls])
    crit = CriticResult(
        finding_id="t1",
        status="CONTRADICTED",
        issues=["ambiguous counterev"],
        recommended_label=None,
    )
    result = apply_critic_results(out, [crit])
    assert result.classifications[0].label == "UNRESOLVED"
    assert result.classifications[0].citation is None


def test_duplicate_drops_the_finding():
    classifications = [
        Classification(id="t1", label="REAL", citation="a:1", note=""),
        Classification(id="t2", label="REAL", citation="a:2", note=""),
    ]
    out = _output_with(classifications=classifications)
    crit = CriticResult(finding_id="t2", status="DUPLICATE", issues=["dup of t1"])
    result = apply_critic_results(out, [crit])
    assert [c.id for c in result.classifications] == ["t1"]


def test_new_trap_weakened_is_dropped_entirely():
    nt = NewTrap(id="t_new_1", hypothesis="h", citation="a:1", note="")
    out = _output_with(new_traps=[nt])
    crit = CriticResult(finding_id="t_new_1", status="WEAKENED")
    result = apply_critic_results(out, [crit])
    assert result.new_traps == []


def test_new_trap_confirmed_is_kept():
    nt = NewTrap(id="t_new_1", hypothesis="h", citation="a:1", note="")
    out = _output_with(new_traps=[nt])
    crit = CriticResult(finding_id="t_new_1", status="CONFIRMED")
    result = apply_critic_results(out, [crit])
    assert len(result.new_traps) == 1


def test_critic_result_without_matching_finding_is_ignored():
    cls = Classification(id="t1", label="REAL", citation="foo.py:5", note="")
    out = _output_with(classifications=[cls])
    crit = CriticResult(finding_id="t_ghost", status="WEAKENED")
    result = apply_critic_results(out, [crit])
    # t1 untouched because critic points at nonexistent id
    assert result.classifications[0].label == "REAL"


def test_critic_results_attached_to_output_for_audit_trail():
    cls = Classification(id="t1", label="REAL", citation="foo.py:5", note="")
    out = _output_with(classifications=[cls])
    crits = [CriticResult(finding_id="t1", status="CONFIRMED")]
    result = apply_critic_results(out, crits)
    assert len(result.critic_results) == 1
    assert result.critic_results[0].finding_id == "t1"
