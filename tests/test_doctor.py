"""Tests for `antemortem doctor` deterministic preflight."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from antemortem.cli import app

runner = CliRunner()


DOC = """---
name: feat
date: 2026-04-21
template: basic
---

# Antemortem - feat

## 1. The change

Add login guard.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | token expiry | trap | 60% | from incident |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/auth.py`
"""


def _write_doc(tmp_path: Path, text: str = DOC) -> Path:
    doc = tmp_path / "feat.md"
    doc.write_text(text, encoding="utf-8")
    return doc


def _write_repo(tmp_path: Path, *, binary: bool = False) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    if binary:
        (repo / "src" / "auth.py").write_bytes(b"\x00\x01\x02")
    else:
        (repo / "src" / "auth.py").write_text(
            "def auth():\n    return True\n",
            encoding="utf-8",
        )
    return repo


def _doctor_json(doc: Path, repo: Path, *extra: str):
    result = runner.invoke(app, ["doctor", str(doc), "--repo", str(repo), "--json", *extra])
    payload = json.loads(result.stdout)
    return result, payload


def test_doctor_valid_document_returns_ready(tmp_path: Path):
    doc = _write_doc(tmp_path)
    repo = _write_repo(tmp_path)

    result, payload = _doctor_json(doc, repo)

    assert result.exit_code == 0
    assert payload["readiness"] == "READY"
    assert payload["schema_frontmatter_status"] == "OK"
    assert payload["spec_length"] == 16
    assert payload["trap_count"] == 1
    assert payload["traps"] == [{"id": "t1", "type": "trap"}]
    assert payload["files_to_read"] == ["src/auth.py"]
    assert payload["missing_files"] == []
    assert payload["files_excluded"] == []
    assert payload["files_loaded"][0]["path"] == "src/auth.py"
    assert payload["total_payload_bytes"] > 0
    assert payload["provider_payload_class"] == "small"


def test_doctor_missing_file_returns_not_ready(tmp_path: Path):
    doc = _write_doc(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()

    result, payload = _doctor_json(doc, repo)

    assert result.exit_code == 1
    assert payload["readiness"] == "NOT_READY"
    assert payload["missing_files"] == ["src/auth.py"]
    assert "missing file: src/auth.py" in payload["warnings"]


def test_doctor_duplicate_trap_ids_warn_or_fail_with_strict(tmp_path: Path):
    duplicate_doc = DOC.replace(
        "| 1 | token expiry | trap | 60% | from incident |",
        "| 1 | token expiry | trap | 60% | from incident |\n"
        "| 1 | refresh race | worry | 20% | duplicate id |",
    )
    doc = _write_doc(tmp_path, duplicate_doc)
    repo = _write_repo(tmp_path)

    loose_result, loose_payload = _doctor_json(doc, repo)
    strict_result, strict_payload = _doctor_json(doc, repo, "--strict")

    assert loose_result.exit_code == 0
    assert loose_payload["readiness"] == "READY_WITH_WARNINGS"
    assert "duplicate trap ids: t1" in loose_payload["warnings"]
    assert strict_result.exit_code == 1
    assert strict_payload["readiness"] == "NOT_READY"


def test_doctor_path_traversal_fails(tmp_path: Path):
    doc = _write_doc(tmp_path, DOC.replace("src/auth.py", "../outside.py"))
    repo = _write_repo(tmp_path)

    result, payload = _doctor_json(doc, repo)

    assert result.exit_code == 1
    assert payload["readiness"] == "NOT_READY"
    assert payload["files_excluded"] == [
        {"path": "../outside.py", "reason": "path escapes repo root"}
    ]
    assert "path traversal attempt: ../outside.py" in payload["warnings"]


def test_doctor_binary_file_is_skipped(tmp_path: Path):
    doc = _write_doc(tmp_path)
    repo = _write_repo(tmp_path, binary=True)

    result, payload = _doctor_json(doc, repo)

    assert result.exit_code == 1
    assert payload["readiness"] == "NOT_READY"
    assert payload["files_excluded"] == [
        {"path": "src/auth.py", "reason": "binary file skipped"}
    ]
    assert "binary file skipped: src/auth.py" in payload["warnings"]


def test_doctor_json_output_stable_snapshot(tmp_path: Path):
    doc = _write_doc(tmp_path)
    repo = _write_repo(tmp_path)

    result, payload = _doctor_json(doc, repo)

    assert result.exit_code == 0
    assert not (doc.with_suffix(".json")).exists()
    snapshot = {
        key: payload[key]
        for key in (
            "schema_frontmatter_status",
            "spec_length",
            "trap_count",
            "traps",
            "files_to_read",
            "missing_files",
            "files_excluded",
            "provider_payload_class",
            "warnings",
            "readiness",
        )
    }
    assert snapshot == {
        "schema_frontmatter_status": "OK",
        "spec_length": 16,
        "trap_count": 1,
        "traps": [{"id": "t1", "type": "trap"}],
        "files_to_read": ["src/auth.py"],
        "missing_files": [],
        "files_excluded": [],
        "provider_payload_class": "small",
        "warnings": [],
        "readiness": "READY",
    }
    output_path = tmp_path / "doctor-report.json"
    output_result = runner.invoke(
        app,
        [
            "doctor",
            str(doc),
            "--repo",
            str(repo),
            "--json-output",
            str(output_path),
            "--json",
        ],
    )
    assert output_result.exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["readiness"] == "READY"
