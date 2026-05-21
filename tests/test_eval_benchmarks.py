# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Offline golden benchmark harness tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from antemortem.cli import app
from antemortem.commands.eval import evaluate_golden_cases


runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "benchmarks" / "golden_cases"


def test_eval_json_outputs_machine_readable_metrics():
    result = runner.invoke(app, ["eval", str(GOLDEN), "--json"])

    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    metrics = payload["metrics"]
    assert metrics["trap_label_accuracy"] == 1.0
    assert metrics["decision_accuracy"] == 1.0
    assert metrics["new_trap_precision"] == 1.0
    assert metrics["citation_valid_rate"] == 9 / 14
    assert metrics["schema_parse_success_rate"] == 15 / 16
    assert metrics["critic_flip_rate"] == 1 / 3
    assert payload["totals"]["cases"] == 16
    assert payload["totals"]["schema_success"] == 15


def test_eval_table_output_is_compact():
    result = runner.invoke(app, ["eval", str(GOLDEN)])

    assert result.exit_code == 0
    assert "trap_label_accuracy" in result.stdout
    assert "schema_parse_success_rate" in result.stdout
    assert "Cases: 16 (15 schema-valid)" in result.stdout


def test_eval_fail_under_exits_nonzero_when_metric_below_threshold():
    result = runner.invoke(
        app,
        [
            "eval",
            str(GOLDEN),
            "--fail-under",
            "citation_valid_rate=1.0",
            "--fail-under",
            "decision_accuracy=0.8",
        ],
    )

    assert result.exit_code == 4
    assert "citation_valid_rate=0.643 below threshold 1.000" in result.stderr
    assert "Why:" in result.stderr
    assert "Next:" in result.stderr


def test_eval_rejects_unknown_threshold_metric():
    result = runner.invoke(
        app,
        ["eval", str(GOLDEN), "--fail-under", "not_a_metric=1.0"],
    )

    assert result.exit_code == 2
    assert "unknown metric" in result.stderr


def test_golden_case_directory_contract():
    required = {"repo", "recon.md", "provider_output.json", "expected.json", "README.md"}
    cases = [path for path in GOLDEN.iterdir() if path.is_dir()]
    assert len(cases) >= 16
    for case_dir in cases:
        assert required <= {path.name for path in case_dir.iterdir()}


def test_adversarial_trust_cases_are_present():
    expected = {
        "wrong_evidence_snippet",
        "citation_range_too_large",
        "path_traversal_citation",
        "binary_file_skipped",
        "symlink_escape_citation",
        "duplicate_trap_ids",
        "missing_file_unresolved",
        "new_trap_valid_evidence_hash",
        "ghost_exact_source_line",
        "high_severity_real_blocks",
    }

    assert expected <= {path.name for path in GOLDEN.iterdir() if path.is_dir()}


def test_metric_denominators_include_expanded_cases():
    result = evaluate_golden_cases(GOLDEN)

    assert result.counters.cases_total == 16
    assert result.counters.schema_success == 15
    assert result.counters.label_total == 16
    assert result.counters.citation_checked == 14
    assert result.counters.expected_traps == 16
    assert result.counters.predicted_new == 2


def test_malformed_cases_do_not_crash_entire_harness():
    result = evaluate_golden_cases(GOLDEN)
    by_name = {case.name: case for case in result.cases}

    assert by_name["malformed_schema_rejected"].schema_parse_success is False
    assert by_name["wrong_evidence_snippet"].schema_parse_success is True
    assert by_name["wrong_evidence_snippet"].citation_checked == 1
    assert result.metrics["schema_parse_success_rate"] == 15 / 16


def test_eval_does_not_call_provider_sdk(monkeypatch):
    def fail_provider_call(*args, **kwargs):  # pragma: no cover - should never run
        raise AssertionError("offline eval must not construct providers")

    import antemortem.providers.factory as factory

    monkeypatch.setattr(factory, "make_provider", fail_provider_call)
    result = evaluate_golden_cases(GOLDEN)

    assert result.metrics["schema_parse_success_rate"] == 15 / 16
