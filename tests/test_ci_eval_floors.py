# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""CI ``eval --fail-under`` policy floors (static + behavioral, no network).

The CI workflow wires four offline-benchmark floors into the
``antemortem eval benchmarks/golden_cases`` step:

  * ``high_severity_block_rate=1.0`` -- absolute invariant (every
    unmitigated high-severity finding must block).
  * ``decision_accuracy=1.0`` and ``trap_label_accuracy=1.0`` -- ratchets
    pinned at the currently-measured golden values.
  * ``citation_valid_rate=0.64`` -- a ratchet, NOT 1.0: the golden
    gallery deliberately ships adversarial invalid-citation cases
    (fabricated / path-traversal / symlink-escape / out-of-range /
    wrong-snippet), so the measured rate is ~0.643. Flooring at 1.0
    would red CI forever.

``false_ghost_rate`` is NOT floored -- low is good there, so ``--fail-under``
(a floor) would fire backwards. It is wired as a ``--fail-over`` CEILING
(``false_ghost_rate=0.0``): the gate fires on metric > value, ratcheted at
the measured 0.0 so any regression that fabricates a ghost reds CI.
"""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from antemortem.cli import app


runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
GOLDEN = ROOT / "benchmarks" / "golden_cases"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


# Single source of truth for the floors the CI step must carry.
ABSOLUTE_FLOORS = {
    "high_severity_block_rate": "1.0",
}
RATCHET_FLOORS = {
    "decision_accuracy": "1.0",
    "trap_label_accuracy": "1.0",
    "citation_valid_rate": "0.64",
}
# Metrics where lower is better get a --fail-over ceiling, not a floor.
RATCHET_CEILINGS = {
    "false_ghost_rate": "0.0",
}


# ---- static: the floors are wired into the workflow ----


def test_ci_eval_step_wires_all_required_floors():
    workflow = _workflow_text()
    for metric, value in {**ABSOLUTE_FLOORS, **RATCHET_FLOORS}.items():
        assert f"--fail-under {metric}={value}" in workflow, metric


def test_ci_eval_invocation_substring_preserved():
    # The base eval invocation substring stays intact so the existing
    # test_ci_workflow contract assertion keeps matching, and the floors
    # are appended after --json (before the redirect).
    workflow = _workflow_text()
    assert "antemortem eval benchmarks/golden_cases --json" in workflow


def test_ci_does_not_floor_false_ghost_rate():
    # Floor-only --fail-under fires backwards on false_ghost_rate (low is
    # good). It must NOT be a floor; it is wired as a --fail-over ceiling.
    workflow = _workflow_text()
    assert "--fail-under false_ghost_rate" not in workflow


def test_ci_eval_step_wires_false_ghost_ceiling():
    workflow = _workflow_text()
    for metric, value in RATCHET_CEILINGS.items():
        assert f"--fail-over {metric}={value}" in workflow, metric


def test_ci_citation_floor_is_ratchet_not_absolute_one():
    # Guard against a future well-meaning "tighten to 1.0" edit: the
    # gallery's adversarial invalid-citation cases make 1.0 impossible.
    workflow = _workflow_text()
    assert "--fail-under citation_valid_rate=1.0" not in workflow


# ---- behavioral: the wired floors actually pass at measured golden ----


def _parse_floors_from_workflow() -> dict[str, float]:
    workflow = _workflow_text()
    pairs = re.findall(r"--fail-under\s+([a-z_]+)=([0-9.]+)", workflow)
    return {name: float(value) for name, value in pairs}


def _parse_ceilings_from_workflow() -> dict[str, float]:
    workflow = _workflow_text()
    pairs = re.findall(r"--fail-over\s+([a-z_]+)=([0-9.]+)", workflow)
    return {name: float(value) for name, value in pairs}


def test_wired_floors_pass_on_current_golden_set():
    floors = _parse_floors_from_workflow()
    assert floors, "expected at least one --fail-under floor in the CI workflow"

    args = ["eval", str(GOLDEN), "--json"]
    for name, value in floors.items():
        args += ["--fail-under", f"{name}={value}"]
    # The wired ceilings (--fail-over) must also pass on the current golden.
    for name, value in _parse_ceilings_from_workflow().items():
        args += ["--fail-over", f"{name}={value}"]

    result = runner.invoke(app, args)
    # exit 0 == every wired floor AND ceiling is met by the current golden metrics.
    assert result.exit_code == 0, result.stderr


def test_floor_above_measured_actually_fails():
    # Proves the gate is real (not vacuous): a floor set above the
    # measured citation_valid_rate must red the gate with exit 4.
    result = runner.invoke(
        app,
        ["eval", str(GOLDEN), "--fail-under", "citation_valid_rate=1.0"],
    )
    assert result.exit_code == 4
    assert "citation_valid_rate=" in result.stderr


def test_ceiling_below_measured_actually_fails():
    # Proves the --fail-over gate is real (not vacuous): a ceiling below the
    # measured citation_valid_rate (~0.643) must red the gate with exit 4.
    result = runner.invoke(
        app,
        ["eval", str(GOLDEN), "--fail-over", "citation_valid_rate=0.5"],
    )
    assert result.exit_code == 4
    assert "above ceiling" in result.stderr


def test_wired_false_ghost_ceiling_passes_on_current_golden_set():
    # The wired false_ghost_rate=0.0 ceiling holds at the measured 0.0.
    result = runner.invoke(
        app,
        ["eval", str(GOLDEN), "--fail-over", "false_ghost_rate=0.0"],
    )
    assert result.exit_code == 0, result.stderr
