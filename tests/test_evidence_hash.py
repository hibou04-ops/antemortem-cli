"""Evidence-bound citation tests.

Line-bound citation checks prove a location exists. Evidence-bound checks
also bind that location to normalized source text via ``evidence_hash`` and
optional ``evidence_snippet``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from antemortem.citations import (
    compute_evidence_hash,
    evidence_hash_for_citation,
    evidence_sha256_for_citation,
    parse_citation,
    read_citation_text,
)
from antemortem.cli import app
from antemortem.commands.lint import run_lint
from antemortem.schema import AntemortemOutput, Classification, NewTrap

runner = CliRunner()


_DOC = """---
name: feat
date: 2026-04-21
template: basic
---

# Antemortem - feat

## 1. The change

Refactor the auth flow.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | token expiry | trap | 60% | from incident |
| 2 | unresolvable | worry | 30% | not in code |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/auth.py`
"""


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text(
        "\n".join(f"auth line {i}" for i in range(1, 21)) + "\n",
        encoding="utf-8",
    )
    return repo


def _write_doc(tmp_path: Path) -> Path:
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    return doc_path


def _write_artifact(doc_path: Path, payload: dict) -> None:
    doc_path.with_suffix(".json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _base_payload(*, evidence_hash: str | None = None) -> dict:
    classification = {
        "id": "t1",
        "label": "REAL",
        "citation": "src/auth.py:5",
        "note": "n",
    }
    if evidence_hash is not None:
        classification["evidence_hash"] = evidence_hash
    return {
        "classifications": [
            classification,
            {"id": "t2", "label": "UNRESOLVED", "citation": None, "note": "n"},
        ],
        "new_traps": [],
        "spec_mutations": [],
        "decision": "PROCEED_WITH_GUARDS",
    }


def _fake_provider(output, usage):
    provider = MagicMock()
    provider.name = "anthropic"
    provider.model = "mock-model"
    provider.structured_complete.return_value = (output, usage)
    return provider


def test_read_citation_text_normalizes_line_endings_and_trailing_whitespace(tmp_path: Path):
    target = tmp_path / "x.py"
    target.write_bytes(b"line 1\r\nline 2   \r\nline 3\r\n")
    parsed = parse_citation("x.py:2")

    assert parsed is not None
    assert read_citation_text(parsed, tmp_path) == "line 2"


def test_compute_evidence_hash_uses_public_sha256_prefix():
    digest = compute_evidence_hash("if user.is_admin:\n    return True\n")

    assert digest.startswith("sha256:")
    assert len(digest.removeprefix("sha256:")) == 64


def test_evidence_hash_for_citation_end_to_end(tmp_path: Path):
    repo = _make_repo(tmp_path)

    digest = evidence_hash_for_citation("src/auth.py:5", repo)

    assert digest == compute_evidence_hash("auth line 5")


def test_legacy_evidence_sha256_helper_remains_traversal_safe(tmp_path: Path):
    outside = tmp_path / "outside.py"
    outside.write_text("secret\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()

    assert evidence_sha256_for_citation("../outside.py:1", repo) is None


def test_lint_passes_valid_evidence_hash_and_snippet(tmp_path: Path):
    doc_path = _write_doc(tmp_path)
    repo = _make_repo(tmp_path)
    expected = evidence_hash_for_citation("src/auth.py:5", repo)
    payload = _base_payload(evidence_hash=expected)
    payload["classifications"][0]["evidence_snippet"] = "auth line 5"
    _write_artifact(doc_path, payload)

    result = run_lint(doc_path, repo, strict_evidence=True)

    assert result.ok, result.violations


def test_lint_fails_when_cited_source_line_changes(tmp_path: Path):
    doc_path = _write_doc(tmp_path)
    repo = _make_repo(tmp_path)
    expected = evidence_hash_for_citation("src/auth.py:5", repo)
    _write_artifact(doc_path, _base_payload(evidence_hash=expected))

    auth_file = repo / "src" / "auth.py"
    lines = auth_file.read_text(encoding="utf-8").splitlines()
    lines[4] = "changed auth line 5"
    auth_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = run_lint(doc_path, repo)

    assert not result.ok
    assert any("hash mismatch" in v for v in result.violations)


def test_lint_fails_when_evidence_snippet_is_not_in_cited_range(tmp_path: Path):
    doc_path = _write_doc(tmp_path)
    repo = _make_repo(tmp_path)
    expected = evidence_hash_for_citation("src/auth.py:5", repo)
    payload = _base_payload(evidence_hash=expected)
    payload["classifications"][0]["evidence_snippet"] = "auth line 6"
    _write_artifact(doc_path, payload)

    result = run_lint(doc_path, repo)

    assert not result.ok
    assert any("snippet not found in cited range" in v for v in result.violations)


def test_lint_strict_evidence_requires_hash_for_non_unresolved(tmp_path: Path):
    doc_path = _write_doc(tmp_path)
    repo = _make_repo(tmp_path)
    _write_artifact(doc_path, _base_payload())

    result = run_lint(doc_path, repo, strict_evidence=True)

    assert not result.ok
    assert any("classification t1: missing evidence_hash" in v for v in result.violations)
    assert not any("classification t2: missing evidence_hash" in v for v in result.violations)


def test_lint_cli_strict_evidence_flag_reports_missing_hash(tmp_path: Path):
    doc_path = _write_doc(tmp_path)
    repo = _make_repo(tmp_path)
    _write_artifact(doc_path, _base_payload())

    result = runner.invoke(
        app,
        ["lint", str(doc_path), "--repo", str(repo), "--strict-evidence"],
    )

    assert result.exit_code == 1
    assert "missing evidence_hash" in result.stderr


def test_lint_default_allows_legacy_artifact_without_evidence_hash(tmp_path: Path):
    doc_path = _write_doc(tmp_path)
    repo = _make_repo(tmp_path)
    _write_artifact(doc_path, _base_payload())

    result = run_lint(doc_path, repo)

    assert result.ok, result.violations


def test_lint_strict_evidence_requires_hash_for_new_traps(tmp_path: Path):
    doc_path = _write_doc(tmp_path)
    repo = _make_repo(tmp_path)
    payload = _base_payload(evidence_hash=evidence_hash_for_citation("src/auth.py:5", repo))
    payload["new_traps"] = [
        {
            "id": "t_new_1",
            "hypothesis": "logging gap",
            "citation": "src/auth.py:7",
            "note": "found",
        }
    ]
    _write_artifact(doc_path, payload)

    result = run_lint(doc_path, repo, strict_evidence=True)

    assert not result.ok
    assert any("new_trap t_new_1: missing evidence_hash" in v for v in result.violations)


def test_lint_rejects_path_traversal_before_evidence_check(tmp_path: Path):
    doc_path = _write_doc(tmp_path)
    repo = _make_repo(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    payload = _base_payload(evidence_hash="sha256:" + "0" * 64)
    payload["classifications"][0]["citation"] = "../outside.py:1"
    _write_artifact(doc_path, payload)

    result = run_lint(doc_path, repo, strict_evidence=True)

    assert not result.ok
    assert any("escapes repo root" in v for v in result.violations)


def test_lint_flags_cited_range_too_large_for_evidence_binding(tmp_path: Path):
    doc_path = _write_doc(tmp_path)
    repo = _make_repo(tmp_path)
    (repo / "src" / "auth.py").write_text(
        "\n".join(f"auth line {i}" for i in range(1, 61)) + "\n",
        encoding="utf-8",
    )
    payload = _base_payload(
        evidence_hash=evidence_hash_for_citation("src/auth.py:1-41", repo)
    )
    payload["classifications"][0]["citation"] = "src/auth.py:1-41"
    _write_artifact(doc_path, payload)

    result = run_lint(doc_path, repo, strict_evidence=True)

    assert not result.ok
    assert any("cited range too large" in v for v in result.violations)


def test_run_populates_evidence_hash_locally_and_preserves_snippet(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = _write_doc(tmp_path)
    repo = _make_repo(tmp_path)
    fake_hash = "sha256:" + "0" * 64

    output = AntemortemOutput(
        classifications=[
            Classification(
                id="t1",
                label="REAL",
                citation="src/auth.py:5",
                note="n",
                evidence_hash=fake_hash,
                evidence_snippet="auth line 5",
            ),
            Classification(id="t2", label="UNRESOLVED", citation=None, note="n"),
        ],
        new_traps=[
            NewTrap(
                id="t_new_1",
                hypothesis="logging gap",
                citation="src/auth.py:7",
                note="found",
                evidence_hash=fake_hash,
            ),
        ],
    )
    fake = _fake_provider(output, {"input_tokens": 1, "output_tokens": 1})

    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(doc_path.with_suffix(".json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in payload["classifications"]}
    assert by_id["t1"]["evidence_hash"] == evidence_hash_for_citation("src/auth.py:5", repo)
    assert by_id["t1"]["evidence_hash"] != fake_hash
    assert by_id["t1"]["evidence_snippet"] == "auth line 5"
    assert by_id["t2"]["evidence_hash"] is None
    assert payload["new_traps"][0]["evidence_hash"] == evidence_hash_for_citation(
        "src/auth.py:7", repo
    )
    strict_lint = run_lint(doc_path, repo, strict_evidence=True)
    assert strict_lint.ok, strict_lint.violations
