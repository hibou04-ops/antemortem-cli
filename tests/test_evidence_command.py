"""Evidence hash maintenance command tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from antemortem.citations import evidence_hash_for_citation
from antemortem.cli import app


runner = CliRunner()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "auth.py").write_text(
        "def check(user):\n"
        "    return user.is_admin\n"
        "def audit():\n"
        "    return True\n",
        encoding="utf-8",
    )
    return repo


def _write_artifact(tmp_path: Path, payload: dict) -> Path:
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return artifact


def _payload(*, evidence_hash: str | None = None) -> dict:
    classification = {
        "id": "t1",
        "label": "REAL",
        "citation": "src/auth.py:2",
        "note": "Admin check is direct.",
    }
    if evidence_hash is not None:
        classification["evidence_hash"] = evidence_hash
    return {
        "classifications": [classification],
        "new_traps": [],
        "spec_mutations": [],
        "critic_results": [],
        "decision": "NEEDS_MORE_EVIDENCE",
        "decision_rationale": "Fixture.",
    }


def test_evidence_writes_missing_hashes(tmp_path: Path):
    repo = _repo(tmp_path)
    artifact = _write_artifact(tmp_path, _payload())

    result = runner.invoke(
        app,
        ["evidence", str(artifact), "--repo", str(repo), "--write-missing", "--json"],
    )

    assert result.exit_code == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["changed"] is True
    assert report["counts"]["missing_hashes"] == 1
    assert report["counts"]["written_hashes"] == 1
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["classifications"][0]["evidence_hash"] == evidence_hash_for_citation(
        "src/auth.py:2",
        repo,
    )


def test_evidence_refuses_path_traversal(tmp_path: Path):
    repo = _repo(tmp_path)
    (tmp_path / "outside.py").write_text("outside = True\n", encoding="utf-8")
    payload = _payload()
    payload["classifications"][0]["citation"] = "../outside.py:1"
    artifact = _write_artifact(tmp_path, payload)

    result = runner.invoke(
        app,
        ["evidence", str(artifact), "--repo", str(repo), "--check", "--json"],
    )

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert report["counts"]["invalid_citations"] == 1
    assert "escapes repo root" in " ".join(report["items"][0]["issues"])


def test_evidence_detects_source_drift(tmp_path: Path):
    repo = _repo(tmp_path)
    expected = evidence_hash_for_citation("src/auth.py:2", repo)
    artifact = _write_artifact(tmp_path, _payload(evidence_hash=expected))
    (repo / "src" / "auth.py").write_text(
        "def check(user):\n"
        "    return False\n"
        "def audit():\n"
        "    return True\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["evidence", str(artifact), "--repo", str(repo), "--check", "--json"],
    )

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["counts"]["mismatched_hashes"] == 1
    assert report["items"][0]["status"] == "mismatched_hash"


def test_evidence_json_output_is_stable(tmp_path: Path):
    repo = _repo(tmp_path)
    expected = evidence_hash_for_citation("src/auth.py:2", repo)
    artifact = _write_artifact(tmp_path, _payload(evidence_hash=expected))

    result = runner.invoke(app, ["evidence", str(artifact), "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert sorted(report) == ["artifact", "changed", "counts", "items", "ok", "repo_root"]
    assert report["items"][0]["status"] == "matching_hash"
    assert report["counts"] == {
        "checked": 1,
        "invalid_citations": 0,
        "matching_hashes": 1,
        "mismatched_hashes": 0,
        "missing_hashes": 0,
        "oversized_ranges": 0,
        "snippet_mismatches": 0,
        "unresolved_skipped": 0,
        "written_hashes": 0,
    }


def test_evidence_handles_unresolved_items(tmp_path: Path):
    repo = _repo(tmp_path)
    payload = {
        "classifications": [
            {
                "id": "t1",
                "label": "UNRESOLVED",
                "citation": None,
                "note": "No supplied evidence.",
            }
        ],
        "new_traps": [],
        "spec_mutations": [],
        "critic_results": [],
        "decision": "NEEDS_MORE_EVIDENCE",
        "decision_rationale": "Fixture.",
    }
    artifact = _write_artifact(tmp_path, payload)

    result = runner.invoke(
        app,
        ["evidence", str(artifact), "--repo", str(repo), "--check", "--json"],
    )

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["counts"]["checked"] == 0
    assert report["counts"]["unresolved_skipped"] == 1
    assert report["items"][0]["status"] == "unresolved_skipped"
