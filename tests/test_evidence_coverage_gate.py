"""Adversarial total-denominator and stored-decision CI regressions."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from antemortem.citation_metrics import compute_citation_metrics
from antemortem.cli import app
from antemortem.decision import DecisionPolicy, compute_decision
from antemortem.schema import AntemortemOutput, Classification


runner = CliRunner()


def _fixture(tmp_path: Path, verified: int = 1, unresolved: int = 9, *, stored="SAFE_TO_PROCEED"):
    (tmp_path / "source.py").write_text("value = 1\n", encoding="utf-8")
    count = verified + unresolved
    rows = "\n".join(f"| {i} | risk {i} | trap | 50% | test |" for i in range(1, count + 1))
    doc = tmp_path / "case.md"
    doc.write_text("""---
name: case
date: 2026-11-02
template: basic
---
## 1. The change
Inspect this reviewed source.
## 2. Traps hypothesized
| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
""" + rows + """
## 3. Recon protocol
- **Files handed to the model:**
  - `source.py`
""", encoding="utf-8")
    output = AntemortemOutput(classifications=[
        *[Classification(id=f"t{i}", label="GHOST", citation="source.py:1")
          for i in range(1, verified + 1)],
        *[Classification(id=f"t{i}", label="UNRESOLVED")
          for i in range(verified + 1, count + 1)],
    ], decision=stored)
    doc.with_suffix(".json").write_text(output.model_dump_json(), encoding="utf-8")
    return doc, output


def _gate(doc, *args):
    return runner.invoke(app, ["gate", str(doc), "--repo", str(doc.parent), "--format", "json", *args])


def test_one_verified_nine_unresolved_uses_all_claims_and_blocks_metrics_and_gate(tmp_path):
    doc, output = _fixture(tmp_path)
    metrics = compute_citation_metrics(output, tmp_path)
    assert (metrics.verified, metrics.fabricated, metrics.unresolved, metrics.total) == (1, 0, 9, 10)
    assert metrics.fabrication_rate == 0
    assert metrics.effective_coverage == 0.1
    assert metrics.unresolved_rate == 0.9
    assert not metrics.ok
    assert compute_decision(output, citation_metrics=metrics).decision == "NEEDS_MORE_EVIDENCE"
    result = _gate(doc, "--allow", "SAFE_TO_PROCEED,NEEDS_MORE_EVIDENCE")
    assert result.exit_code == 4
    assert json.loads(result.stdout)["deployment_authorized"] is False
    result = runner.invoke(app, ["metrics", str(doc.with_suffix(".json")), "--repo", str(tmp_path), "--fail-over", "0"])
    assert result.exit_code == 4


def test_gate_does_not_allow_lowering_coverage_floor(tmp_path):
    doc, _ = _fixture(tmp_path, stored="NEEDS_MORE_EVIDENCE")
    result = _gate(doc, "--allow", "NEEDS_MORE_EVIDENCE", "--min-effective-coverage", "0")
    assert result.exit_code != 0


def test_forged_safe_and_supplied_counts_cannot_replace_current_evidence(tmp_path):
    doc, _ = _fixture(tmp_path)
    path = doc.with_suffix(".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update({"effective_coverage": 1, "verified": 1000, "unresolved": 0,
                    "citation_metrics": {"ok": True, "verified": 1000, "total": 1000}})
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = _gate(doc)
    data = json.loads(result.stdout)
    assert result.exit_code == 4
    assert data["citation_metrics"]["verified"] == 1
    assert data["citation_metrics"]["unresolved"] == 9
    assert data["computed_decision"] == "NEEDS_MORE_EVIDENCE"
    assert data["stored_decision"] == "SAFE_TO_PROCEED"


def test_forged_decision_fails_even_with_complete_evidence_and_expanded_allowlist(tmp_path):
    doc, output = _fixture(tmp_path, 10, 0)
    output.classifications = [
        Classification(id=f"t{i}", label="REAL", citation="source.py:1")
        for i in range(1, 11)
    ]
    doc.with_suffix(".json").write_text(output.model_dump_json(), encoding="utf-8")
    assert compute_citation_metrics(output, tmp_path).ok
    result = _gate(doc, "--allow", "SAFE_TO_PROCEED,PROCEED_WITH_GUARDS,NEEDS_MORE_EVIDENCE")
    assert result.exit_code == 4
    assert "differs from recomputed" in json.loads(result.stdout)["reason"]


@pytest.mark.parametrize("verified,unresolved,passed", [(0, 0, False), (0, 10, False), (7, 3, False), (8, 2, True), (10, 0, True)])
def test_coverage_boundary_and_zero_evidence(tmp_path, verified, unresolved, passed):
    doc, output = _fixture(tmp_path, verified, unresolved)
    metrics = compute_citation_metrics(output, tmp_path)
    assert metrics.ok is passed
    result = _gate(doc)
    assert (result.exit_code == 0) is passed


@pytest.mark.parametrize("extra", [[], ["--no-require-artifact"]])
def test_missing_artifact_never_authorizes(tmp_path, extra):
    doc, _ = _fixture(tmp_path, 1, 0)
    doc.with_suffix(".json").unlink()
    result = _gate(doc, *extra)
    assert result.exit_code != 0
    assert json.loads(result.stdout)["deployment_authorized"] is False


@pytest.mark.parametrize("payload", ["not JSON", "{}", '{"classifications": []}'])
def test_malformed_missing_or_empty_classifications_never_authorize(tmp_path, payload):
    doc, _ = _fixture(tmp_path, 1, 0)
    doc.with_suffix(".json").write_text(payload, encoding="utf-8")
    result = _gate(doc)
    assert result.exit_code != 0
    assert json.loads(result.stdout)["deployment_authorized"] is False


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan"), float("inf"), True, "0.8"])
def test_invalid_coverage_policy_is_rejected(value):
    with pytest.raises(ValueError):
        DecisionPolicy(min_effective_coverage=value)


def test_high_severity_block_precedes_coverage_failure(tmp_path):
    _, output = _fixture(tmp_path)
    output.classifications[0] = Classification(id="t1", label="REAL", severity="high", citation="source.py:1")
    assert compute_decision(output, citation_metrics=compute_citation_metrics(output, tmp_path)).decision == "DO_NOT_PROCEED"


def test_deleted_disk_evidence_cannot_be_rescued_by_stored_metrics(tmp_path):
    doc, _ = _fixture(tmp_path, 1, 0)
    (tmp_path / "source.py").unlink()
    result = _gate(doc, "--allow", "SAFE_TO_PROCEED,NEEDS_MORE_EVIDENCE")
    data = json.loads(result.stdout)
    assert result.exit_code != 0
    assert data["citation_metrics"]["fabricated"] == 1
    assert data["deployment_authorized"] is False


def test_explicit_allowlist_keeps_its_business_decision_policy(tmp_path):
    doc, output = _fixture(tmp_path, 1, 0, stored="DO_NOT_PROCEED")
    output.classifications[0] = Classification(id="t1", label="REAL", severity="high", citation="source.py:1")
    doc.with_suffix(".json").write_text(output.model_dump_json(), encoding="utf-8")
    # The caller may override a business label, but cannot waive the mandatory
    # evidence/coverage/consistency checks tested above. This is not a safety proof.
    assert _gate(doc, "--allow", "DO_NOT_PROCEED").exit_code == 0


def test_artifact_change_after_lint_cannot_authorize(tmp_path, monkeypatch):
    import importlib
    gate_module = importlib.import_module("antemortem.commands.gate")
    doc, _ = _fixture(tmp_path, 1, 0)
    original = gate_module.run_lint

    def change_after_lint(*args, **kwargs):
        result = original(*args, **kwargs)
        doc.with_suffix(".json").write_text("{}", encoding="utf-8")
        return result

    monkeypatch.setattr(gate_module, "run_lint", change_after_lint)
    result = _gate(doc)
    assert result.exit_code != 0
    assert "changed during verification" in json.loads(result.stdout)["reason"]


def test_duplicate_verified_rows_cannot_inflate_coverage(tmp_path):
    doc, output = _fixture(tmp_path, 1, 1)
    # A duplicated verified ID must not turn actual 1/2 coverage into 4/5.
    payload = output.model_dump()
    payload["classifications"] = [payload["classifications"][0]] * 4 + [payload["classifications"][1]]
    doc.with_suffix(".json").write_text(json.dumps(payload), encoding="utf-8")
    metrics = compute_citation_metrics(AntemortemOutput.model_validate(payload), tmp_path)
    assert metrics.effective_coverage == 0.8
    assert metrics.finding_ids_unique is False
    assert metrics.ok is False
    assert compute_decision(AntemortemOutput.model_validate(payload), citation_metrics=metrics).decision == "NEEDS_MORE_EVIDENCE"
    metric_result = runner.invoke(app, ["metrics", str(doc.with_suffix(".json")), "--repo", str(tmp_path)])
    assert metric_result.exit_code == 4
    result = _gate(doc)
    assert result.exit_code != 0
    assert "duplicate finding id" in json.loads(result.stdout)["reason"]


@pytest.mark.parametrize("unresolved", [0, 10])
def test_metrics_empty_or_all_unresolved_never_pass_default_policy(tmp_path, unresolved):
    doc, _ = _fixture(tmp_path, 0, unresolved)
    result = runner.invoke(app, ["metrics", str(doc.with_suffix(".json")), "--repo", str(tmp_path), "--format", "json"])
    assert result.exit_code == 4
    assert json.loads(result.stdout)["ok"] is False


def test_keyless_demo_asserts_the_real_cli_boundary():
    script = Path(__file__).resolve().parents[1] / "examples" / "reproduce_citation_traps.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 0, result.stderr
    cases = {case["case"]: case for case in json.loads(result.stdout)}
    assert cases["unresolved_denominator"]["effective_coverage"] == 0.1
    assert cases["unresolved_denominator"]["fabrication_rate"] == 0
    assert cases["forged_safe_decision"]["deployment_authorized"] is False
    assert cases["empty_evidence"]["deployment_authorized"] is False
    assert cases["complete_verified_evidence"]["deployment_authorized"] is True
