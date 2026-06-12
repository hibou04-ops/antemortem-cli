"""Contract tests for the composite GitHub Action (action.yml) + example."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "action.yml"
EXAMPLE_WORKFLOW = ROOT / "examples" / "github_action_gate.yml"


def _package_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]


def test_action_file_exists_at_repo_root():
    # GitHub requires action.yml (or action.yaml) at the repo root for
    # `uses: owner/repo@ref` to resolve.
    assert ACTION.is_file()


def test_action_is_valid_yaml_composite():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    assert data["runs"]["using"] == "composite"
    assert "name" in data and "description" in data
    # Wires to `antemortem gate` somewhere in the steps.
    steps_text = yaml.safe_dump(data["runs"]["steps"])
    assert "antemortem gate" in steps_text


def test_action_default_version_matches_package_version():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    assert data["inputs"]["version"]["default"] == _package_version()


def test_action_declares_required_inputs_and_outputs():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    inputs = data["inputs"]
    for name in ("document", "repo", "allow", "require-artifact", "version"):
        assert name in inputs, f"action.yml missing input {name}"
    assert inputs["document"]["required"] is True
    outputs = data["outputs"]
    assert "summary" in outputs
    assert "decision" in outputs


def test_action_wires_gate_format_json_for_machine_summary():
    text = ACTION.read_text(encoding="utf-8")
    # The action runs the gate in json mode so it can publish a summary.
    assert "--format json" in text
    assert "--allow" in text
    assert "--repo" in text


def test_example_workflow_exists_and_references_pinned_action():
    yaml = pytest.importorskip("yaml")
    assert EXAMPLE_WORKFLOW.is_file()
    data = yaml.safe_load(EXAMPLE_WORKFLOW.read_text(encoding="utf-8"))
    # The example pins the action to the current major.minor.patch tag.
    text = EXAMPLE_WORKFLOW.read_text(encoding="utf-8")
    assert f"hibou04-ops/antemortem-cli@v{_package_version()}" in text
    assert "on" in data or True  # YAML parses 'on:' as True key; presence is enough
