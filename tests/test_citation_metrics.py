"""Tests for fabricated-citation metrics (citation_metrics module + commands)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from antemortem.citation_metrics import (
    compute_citation_metrics,
    metrics_from_artifact,
)
from antemortem.citations import evidence_hash_for_citation
from antemortem.cli import app
from antemortem.schema import AntemortemOutput, Classification, NewTrap

runner = CliRunner()


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "auth.py").write_text(
        "\n".join(f"auth line {i}" for i in range(1, 21)) + "\n",
        encoding="utf-8",
    )
    return repo


def test_metrics_all_verified(tmp_path: Path):
    repo = _make_repo(tmp_path)
    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
            Classification(id="t2", label="GHOST", citation="src/auth.py:10", note="n"),
            Classification(id="t3", label="UNRESOLVED", citation=None, note="no evidence"),
        ],
        new_traps=[
            NewTrap(id="t_new_1", hypothesis="x", citation="src/auth.py:15", note="n"),
        ],
    )
    m = compute_citation_metrics(output, repo)
    assert m.verified == 3
    assert m.fabricated == 0
    assert m.unresolved == 1
    assert m.cited == 3
    assert m.total == 4
    assert m.fabrication_rate == 0.0
    assert m.ok is True


def test_metrics_detects_fabricated_bad_path(tmp_path: Path):
    repo = _make_repo(tmp_path)
    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/ghost.py:5", note="n"),
            Classification(id="t2", label="GHOST", citation="src/auth.py:10", note="n"),
        ],
    )
    m = compute_citation_metrics(output, repo)
    assert m.verified == 1
    assert m.fabricated == 1
    assert m.ok is False
    fabricated = [f for f in m.findings if f.status == "fabricated"]
    assert fabricated[0].id == "t1"
    assert "does not exist" in fabricated[0].reason


def test_metrics_detects_fabricated_out_of_range(tmp_path: Path):
    repo = _make_repo(tmp_path)
    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:9999", note="n"),
        ],
    )
    m = compute_citation_metrics(output, repo)
    assert m.fabricated == 1
    assert m.verified == 0


def test_metrics_detects_stale_evidence_hash(tmp_path: Path):
    repo = _make_repo(tmp_path)
    # A correct hash for the cited range makes it verified...
    good_hash = evidence_hash_for_citation("src/auth.py:5", repo)
    verified = AntemortemOutput(
        classifications=[
            Classification(
                id="t1", label="REAL", citation="src/auth.py:5", note="n",
                evidence_hash=good_hash,
            ),
        ],
    )
    assert compute_citation_metrics(verified, repo).verified == 1

    # ...but a hash that no longer matches the cited text is a fabrication
    # (the evidence drifted) even though the line range still resolves.
    stale = AntemortemOutput(
        classifications=[
            Classification(
                id="t1", label="REAL", citation="src/auth.py:5", note="n",
                evidence_hash="sha256:" + "0" * 64,
            ),
        ],
    )
    m = compute_citation_metrics(stale, repo)
    assert m.fabricated == 1
    assert "evidence_hash mismatch" in m.findings[0].reason


def test_metrics_json_schema_is_stable(tmp_path: Path):
    repo = _make_repo(tmp_path)
    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
        ],
    )
    j = compute_citation_metrics(output, repo).to_json()
    assert j["schema"] == "antemortem-citation-metrics-v1"
    for key in ("verified", "fabricated", "unresolved", "cited", "total",
                "fabrication_rate", "verified_rate", "ok", "findings"):
        assert key in j


def _write_artifact(tmp_path: Path, classifications: list[dict]) -> Path:
    artifact = tmp_path / "feat.json"
    artifact.write_text(
        json.dumps(
            {
                "classifications": classifications,
                "new_traps": [],
                "spec_mutations": [],
            }
        ),
        encoding="utf-8",
    )
    return artifact


def test_metrics_from_artifact_roundtrip(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/auth.py:5", "note": "n"}],
    )
    m = metrics_from_artifact(artifact, repo)
    assert m.verified == 1


def test_metrics_command_text_pass(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/auth.py:5", "note": "n"}],
    )
    result = runner.invoke(app, ["metrics", str(artifact), "--repo", str(repo)])
    assert result.exit_code == 0, result.stdout
    assert "verified=1" in result.stdout
    assert "Status: PASS" in result.stdout


def test_metrics_command_json(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/ghost.py:5", "note": "n"}],
    )
    result = runner.invoke(
        app, ["metrics", str(artifact), "--repo", str(repo), "--format", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["fabricated"] == 1
    assert data["ok"] is False


def test_metrics_command_fail_over_zero_tolerance(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/ghost.py:5", "note": "n"}],
    )
    result = runner.invoke(
        app, ["metrics", str(artifact), "--repo", str(repo), "--fail-over", "0"]
    )
    assert result.exit_code == 4  # POLICY_GATE_FAILURE
    assert "fabrication rate" in result.stderr


def test_metrics_command_fail_over_passes_when_clean(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/auth.py:5", "note": "n"}],
    )
    result = runner.invoke(
        app, ["metrics", str(artifact), "--repo", str(repo), "--fail-over", "0"]
    )
    assert result.exit_code == 0


def test_metrics_command_rejects_bad_format(tmp_path: Path):
    repo = _make_repo(tmp_path)
    artifact = _write_artifact(
        tmp_path,
        [{"id": "t1", "label": "REAL", "citation": "src/auth.py:5", "note": "n"}],
    )
    result = runner.invoke(
        app, ["metrics", str(artifact), "--repo", str(repo), "--format", "xml"]
    )
    assert result.exit_code == 2
