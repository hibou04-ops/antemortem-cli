"""Operational citation I/O, mutation and evidence-contract regressions."""

from contextlib import contextmanager
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from antemortem.citations import (
    CitationVerifier, ParsedCitation, audit_output_citations, compute_evidence_hash,
    evidence_hash_for_citation, read_citation_text, verify_citation,
)
from antemortem.citation_metrics import compute_citation_metrics
from antemortem.cli import app
from antemortem.commands.lint import run_lint
from antemortem.schema import AntemortemOutput, Classification
from tests.test_format_json import _setup


def _output(**binding):
    return AntemortemOutput(classifications=[
        Classification(id="t1", label="REAL", citation="source.py:2", **binding),
    ])


@pytest.mark.parametrize("command", ["lint", "gate"])
def test_json_commands_read_repeated_source_once(tmp_path, monkeypatch, command):
    rows = [dict(id=f"t{i}", label="REAL", citation="src/auth.py:5", note="n",
                 evidence_hash=compute_evidence_hash("auth line 5")) for i in range(1, 101)]
    doc, repo = _setup(tmp_path, rows, decision="PROCEED_WITH_GUARDS")
    text = doc.read_text(encoding="utf-8")
    text = text.replace("| 1 | token expiry | trap | 60% | from incident |",
                        "\n".join(f"| {i} | risk {i} | trap | 60% | n |" for i in range(1, 101)))
    doc.write_text(text, encoding="utf-8")
    source = repo / "src" / "auth.py"
    original = Path.open
    reads = []

    def observe(path, *args, **kwargs):
        if path == source:
            reads.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observe)
    result = CliRunner().invoke(app, [command, str(doc), "--repo", str(repo), "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["citation_metrics"]["verified"] == 100
    assert len(reads) == 1


def test_metrics_reuses_one_file_for_distinct_ranges(tmp_path, monkeypatch):
    source = tmp_path / "source.py"
    source.write_text("one\ntwo\nthree\n", encoding="utf-8")
    output = AntemortemOutput(classifications=[
        Classification(id=f"t{i}", label="REAL", citation=f"source.py:{i}") for i in range(1, 4)
    ])
    original = Path.open
    reads = []

    def observe(path, *args, **kwargs):
        if path == source:
            reads.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observe)
    assert compute_citation_metrics(output, tmp_path).verified == 3
    assert len(reads) == 1


@pytest.mark.parametrize("change", ["edit", "delete", "move"])
def test_existing_session_rejects_changed_source_and_next_operation_rechecks(tmp_path, change):
    source = tmp_path / "source.py"
    source.write_text("one\ntwo\n", encoding="utf-8")
    verifier = CitationVerifier(tmp_path)
    assert verifier.verify("source.py:2").ok
    if change == "edit":
        source.write_text("one\nchanged two\n", encoding="utf-8")
    elif change == "delete":
        source.unlink()
    else:
        source.rename(tmp_path / "moved.py")
    assert not verifier.verify("source.py:2").ok
    assert verifier.read(ParsedCitation("source.py", 2, 2)) is None
    if change == "edit":
        assert read_citation_text(ParsedCitation("source.py", 2, 2), tmp_path) == "changed two"
    else:
        assert not verify_citation("source.py:2", tmp_path).ok


def test_edit_during_read_is_a_failure(tmp_path, monkeypatch):
    source = tmp_path / "source.py"
    source.write_text("one\ntwo\n", encoding="utf-8")
    original = Path.open

    @contextmanager
    def mutate(path, *args, **kwargs):
        with original(path, *args, **kwargs) as handle:
            yield handle
        if path == source:
            with original(source, "w", encoding="utf-8") as writer:
                writer.write("changed source\n")

    monkeypatch.setattr(Path, "open", mutate)
    result = verify_citation("source.py:2", tmp_path)
    assert not result.ok
    assert "changed during verification" in result.reason


def test_permission_failure_is_structured_in_every_reader(tmp_path, monkeypatch):
    source = tmp_path / "source.py"
    source.write_text("one\ntwo\n", encoding="utf-8")
    original = Path.open

    def deny(path, *args, **kwargs):
        if path == source:
            raise PermissionError("test: access denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)
    assert "could not be read" in verify_citation("source.py:2", tmp_path).reason
    assert read_citation_text(ParsedCitation("source.py", 2, 2), tmp_path) is None
    metrics = compute_citation_metrics(_output(), tmp_path)
    assert metrics.fabricated == 1
    assert "could not be read" in metrics.findings[0].reason


@pytest.mark.parametrize("data", [b"one\r\ntwo\r\n", b"one\rtwo\r", b"one\ntwo", b"one\vtwo\nlast\n", b"one\xff\ntwo\n"])
def test_bounds_and_evidence_use_identical_newline_and_decoding_rules(tmp_path, data):
    (tmp_path / "source.py").write_bytes(data)
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    expected = text.split("\n")[1].rstrip()
    assert verify_citation("source.py:2", tmp_path).ok
    assert read_citation_text(ParsedCitation("source.py", 2, 2), tmp_path) == expected
    assert evidence_hash_for_citation("source.py:2", tmp_path) == compute_evidence_hash(expected)


@pytest.mark.parametrize("binding,reason", [
    ({"evidence_snippet": "not in the source"}, "snippet not found"),
    ({"evidence_sha256": "0" * 64}, "hash mismatch"),
    ({"evidence_hash": "sha256:" + "0" * 64}, "evidence_hash mismatch"),
])
def test_metrics_and_runtime_audit_reject_same_evidence_as_lint(tmp_path, binding, reason):
    (tmp_path / "source.py").write_text("one\ntwo\n", encoding="utf-8")
    output = _output(**binding)
    metrics = compute_citation_metrics(output, tmp_path)
    audit = audit_output_citations(output, tmp_path)
    assert metrics.fabricated == 1
    assert reason in metrics.findings[0].reason
    assert not audit.ok
    assert any(reason in violation for violation in audit.violations)


def test_large_file_streaming_and_eviction_preserve_exact_bounds(tmp_path):
    for name in ("source.py", "other.py"):
        (tmp_path / name).write_text("".join(f"line {i}\n" for i in range(1000)), encoding="utf-8")
    verifier = CitationVerifier(tmp_path, max_cache_bytes=32)
    assert verifier.verify("source.py:999-1000").ok
    assert verifier.read(ParsedCitation("source.py", 999, 1000)) == "line 998\nline 999"
    assert verifier.verify("other.py:1").ok
    assert not verifier.verify("source.py:1001").ok
    assert verifier.read(ParsedCitation("source.py", 1, 1)) == "line 0"


def test_symlink_escape_is_rejected_before_open(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    try:
        (root / "link.py").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks require platform permission")
    assert "escapes" in CitationVerifier(root).verify("link.py:1").reason


def test_lint_unreadable_bound_evidence_fails_closed(tmp_path, monkeypatch):
    rows = [dict(id="t1", label="REAL", citation="src/auth.py:5", note="n",
                 evidence_hash=compute_evidence_hash("auth line 5"))]
    doc, repo = _setup(tmp_path, rows)
    source = repo / "src" / "auth.py"
    original = Path.open

    def deny(path, *args, **kwargs):
        if path == source:
            raise PermissionError("test: access denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)
    result = run_lint(doc, repo)
    assert not result.ok
    assert any("could not be read" in v for v in result.violations)


def test_reader_cannot_be_borrowed_to_bypass_another_repo_root(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "source.py").write_text("outside the second repo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="different repo root"):
        verify_citation("source.py:1", second, verifier=CitationVerifier(first))
