"""Tests for the public README claim ledger."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_claim_ledger.py"
SPEC = importlib.util.spec_from_file_location("check_claim_ledger", SCRIPT_PATH)
assert SPEC is not None
check_claim_ledger = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_claim_ledger
SPEC.loader.exec_module(check_claim_ledger)


def _write_fixture_readmes(root: Path, text: str = "Claim ledger docs/claim_ledger.md docs/claim_ledger_kr.md\n") -> None:
    for rel in check_claim_ledger.README_FILES:
        (root / rel).write_text(text, encoding="utf-8")


def _write_ledger(root: Path, body: str) -> None:
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "claim_ledger.md").write_text(
        "| Claim | Location | Source of truth | Verification command | Status |\n"
        "|---|---|---|---|---|\n"
        + body,
        encoding="utf-8",
    )


def test_current_claim_ledgers_pass():
    issues = check_claim_ledger.check_claim_ledger(ROOT)

    assert issues == []


def test_claim_without_source_fails(tmp_path: Path):
    _write_fixture_readmes(tmp_path, "Version claim docs/claim_ledger.md docs/claim_ledger_kr.md\n")
    _write_ledger(
        tmp_path,
        "| version claim | README.md:Version claim |  | python scripts/check_repo_consistency.py | source-backed |\n",
    )

    issues = check_claim_ledger.check_claim_ledger(
        tmp_path,
        ledger_files=("docs/claim_ledger.md",),
        readme_files=("README.md",),
        check_required=False,
    )

    assert any(issue.code == "missing-field" for issue in issues)
    assert any(issue.code == "unbacked-claim" for issue in issues)


def test_qualitative_claim_must_be_marked_qualitative(tmp_path: Path):
    _write_fixture_readmes(tmp_path, "Workflow guidance docs/claim_ledger.md docs/claim_ledger_kr.md\n")
    _write_ledger(
        tmp_path,
        "| workflow guidance | README.md:Workflow guidance | qualitative statement marker | n/a qualitative | source-backed |\n",
    )

    issues = check_claim_ledger.check_claim_ledger(
        tmp_path,
        ledger_files=("docs/claim_ledger.md",),
        readme_files=("README.md",),
        check_required=False,
    )

    assert any(issue.code == "qualitative-unmarked" for issue in issues)


def test_location_fragment_drift_fails(tmp_path: Path):
    _write_fixture_readmes(tmp_path, "Current claim docs/claim_ledger.md docs/claim_ledger_kr.md\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nversion='1.0.0'\n", encoding="utf-8")
    _write_ledger(
        tmp_path,
        "| version claim | README.md:Missing fragment | pyproject.toml | python scripts/check_repo_consistency.py | source-backed |\n",
    )

    issues = check_claim_ledger.check_claim_ledger(
        tmp_path,
        ledger_files=("docs/claim_ledger.md",),
        readme_files=("README.md",),
        check_required=False,
    )

    assert [issue.code for issue in issues] == ["location-drift"]


def test_readme_variants_must_reference_claim_ledgers(tmp_path: Path):
    _write_fixture_readmes(tmp_path, "No ledger link\n")
    (tmp_path / "docs").mkdir(exist_ok=True)
    for rel in check_claim_ledger.LEDGER_FILES:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "| Claim | Location | Source of truth | Verification command | Status |\n"
            "|---|---|---|---|---|\n"
            "| version claim | README.md:No ledger link | pyproject.toml | python scripts/check_repo_consistency.py | source-backed |\n",
            encoding="utf-8",
        )
    (tmp_path / "pyproject.toml").write_text("[project]\nversion='1.0.0'\n", encoding="utf-8")

    issues = check_claim_ledger.check_claim_ledger(tmp_path, check_required=True)

    assert any(issue.code == "missing-ledger-reference" for issue in issues)
