"""Citation parsing and disk-verification tests."""

from pathlib import Path

from antemortem.citations import (
    ParsedCitation,
    parse_citation,
    verify_citation,
)


def test_parse_single_line():
    p = parse_citation("src/foo.py:42")
    assert p == ParsedCitation(path="src/foo.py", start=42, end=42)


def test_parse_line_range():
    p = parse_citation("src/foo.py:10-20")
    assert p == ParsedCitation(path="src/foo.py", start=10, end=20)


def test_parse_normalizes_windows_backslash():
    p = parse_citation(r"src\foo.py:5")
    assert p is not None
    assert p.path == "src/foo.py"
    assert p.start == 5


def test_parse_rejects_no_line_number():
    assert parse_citation("src/foo.py") is None


def test_parse_rejects_empty_string():
    assert parse_citation("") is None


def test_parse_rejects_prose():
    assert parse_citation("see the walk_forward module") is None


def test_parse_rejects_zero_line():
    assert parse_citation("foo.py:0") is None


def test_parse_rejects_reversed_range():
    assert parse_citation("foo.py:20-10") is None


def test_verify_ok_for_existing_file(tmp_path: Path):
    target = tmp_path / "sample.py"
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")
    result = verify_citation("sample.py:2", tmp_path)
    assert result.ok, result.reason
    assert result.parsed is not None
    assert result.parsed.start == 2


def test_verify_ok_for_range_within_bounds(tmp_path: Path):
    target = tmp_path / "sample.py"
    target.write_text("a\nb\nc\nd\n", encoding="utf-8")
    result = verify_citation("sample.py:1-4", tmp_path)
    assert result.ok, result.reason


def test_verify_fails_nonexistent_file(tmp_path: Path):
    result = verify_citation("ghost.py:1", tmp_path)
    assert not result.ok
    assert "does not exist" in result.reason


def test_verify_fails_out_of_range(tmp_path: Path):
    target = tmp_path / "sample.py"
    target.write_text("only one line\n", encoding="utf-8")
    result = verify_citation("sample.py:5", tmp_path)
    assert not result.ok
    assert "out of range" in result.reason


def test_verify_fails_path_traversal(tmp_path: Path):
    outside = tmp_path / "outside.py"
    outside.write_text("x\n", encoding="utf-8")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    result = verify_citation("../outside.py:1", repo_root)
    assert not result.ok
    assert "escapes" in result.reason


def test_verify_fails_invalid_format(tmp_path: Path):
    result = verify_citation("no-colon", tmp_path)
    assert not result.ok
    assert "invalid format" in result.reason
