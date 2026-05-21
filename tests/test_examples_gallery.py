"""Executable checks for the offline CLI example gallery."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from antemortem.cli import app
from antemortem.exit_codes import POLICY_GATE_FAILURE


ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "examples" / "gallery"
CASES = {
    "risky_refactor_preflight",
    "agent_generated_patch_review",
    "security_sensitive_change",
    "missing_evidence_unresolved",
    "ci_gate_blocking_merge",
}


runner = CliRunner()


def _case_dirs() -> list[Path]:
    return sorted(path for path in GALLERY.iterdir() if path.is_dir())


def test_gallery_has_expected_case_structure():
    case_dirs = _case_dirs()

    assert {path.name for path in case_dirs} == CASES
    for case in case_dirs:
        assert (case / "README.md").is_file()
        assert (case / "recon.md").is_file()
        assert (case / "recon.json").is_file()
        assert (case / "repo").is_dir()
        assert any(path.is_file() for path in (case / "repo").rglob("*"))
        readme = (case / "README.md").read_text(encoding="utf-8")
        assert "antemortem lint" in readme


def test_gallery_outputs_lint_offline_without_provider_calls():
    for case in _case_dirs():
        result = runner.invoke(
            app,
            ["lint", str(case / "recon.md"), "--repo", str(case / "repo")],
        )

        assert result.exit_code == 0, f"{case.name}: {result.stdout}\n{result.stderr}"
        assert "PASS -- recon.md validates clean" in result.stdout


def test_gallery_artifacts_have_evidence_hashes_except_unresolved():
    for case in _case_dirs():
        payload = json.loads((case / "recon.json").read_text(encoding="utf-8"))
        for item in payload["classifications"]:
            if item["label"] == "UNRESOLVED":
                assert item["citation"] is None
                assert "evidence_hash" not in item
            else:
                assert item["citation"]
                assert item["evidence_hash"].startswith("sha256:")
                assert item["evidence_snippet"]


def test_ci_gate_example_blocks_merge_after_lint_passes():
    case = GALLERY / "ci_gate_blocking_merge"

    lint_result = runner.invoke(
        app,
        ["lint", str(case / "recon.md"), "--repo", str(case / "repo")],
    )
    gate_result = runner.invoke(
        app,
        ["gate", str(case / "recon.md"), "--repo", str(case / "repo")],
    )

    assert lint_result.exit_code == 0
    assert gate_result.exit_code == POLICY_GATE_FAILURE
    assert "DO_NOT_PROCEED" in gate_result.stderr


def test_examples_docs_link_every_case():
    english = (ROOT / "docs" / "examples.md").read_text(encoding="utf-8")
    korean = (ROOT / "docs" / "examples_kr.md").read_text(encoding="utf-8")
    for case in CASES:
        assert case in english
        assert case in korean
