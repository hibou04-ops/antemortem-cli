# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Offline symbol grounding checks use AST declarations rather than text."""

from pathlib import Path

import pytest

from antemortem.citations import verify_ast_symbol_grounding


SOURCE = (
    "def calculate(value):\n"
    "    return value + 1\n"
    "\n"
    "async def fetch():\n"
    "    return 2\n"
    "\n"
    "class Ledger:\n"
    "    total: int = 3\n"
    "\n"
    "threshold = (\n"
    "    4\n"
    ")\n"
    "first = second = 5\n"
    "left, (middle, right) = (1, (2, 3))\n"
    "limit: int\n"
    "description = 'ghost'\n"
    "alias = calculate\n"
    "record.field = 6\n"
    "bucket[index] = 7\n"
)


@pytest.fixture
def source_path(tmp_path: Path) -> Path:
    target = tmp_path / "example.py"
    target.write_text(SOURCE, encoding="utf-8")
    return target


@pytest.mark.parametrize(
    ("symbol", "start", "end"),
    [
        ("calculate", 1, 1),
        ("calculate", 2, 2),
        ("calculate", 2, 4),
        ("fetch", 4, 5),
        ("Ledger", 7, 8),
        ("total", 8, 8),
        ("threshold", 10, 10),
        ("threshold", 11, 11),
        ("threshold", 12, 12),
        ("first", 13, 13),
        ("second", 13, 13),
        ("left", 14, 14),
        ("middle", 14, 14),
        ("right", 14, 14),
        ("limit", 15, 15),
        ("alias", 17, 17),
    ],
)
def test_matches_definition_or_assignment(source_path: Path, symbol: str, start: int, end: int):
    assert verify_ast_symbol_grounding(source_path, start, end, symbol)


@pytest.mark.parametrize(
    ("symbol", "start", "end"),
    [
        ("missing", 1, 2),
        ("Calculate", 1, 2),
        ("calculate", 3, 3),
        ("fetch", 1, 2),
        ("threshold", 9, 9),
        ("threshold", 13, 13),
        ("ghost", 16, 16),
        ("calculate", 17, 17),
        ("record", 18, 18),
        ("field", 18, 18),
        ("bucket", 19, 19),
        ("index", 19, 19),
        ("", 1, 2),
        ("calculate", 0, 2),
        ("calculate", -1, 2),
        ("calculate", 2, 1),
        ("calculate", 1, 20),
    ],
)
def test_rejects_wrong_symbol_or_invalid_range(
    source_path: Path, symbol: str, start: int, end: int
):
    assert not verify_ast_symbol_grounding(source_path, start, end, symbol)


@pytest.mark.parametrize("source", ["def broken(:\n", "", "value = '\x00'\n"])
def test_invalid_python_is_not_grounded(tmp_path: Path, source: str):
    target = tmp_path / "broken.py"
    target.write_text(source, encoding="utf-8")
    assert not verify_ast_symbol_grounding(target, 1, 1, "value")


def test_missing_source_is_not_grounded(tmp_path: Path):
    assert not verify_ast_symbol_grounding(tmp_path / "missing.py", 1, 1, "value")


def test_directory_is_not_grounded(tmp_path: Path):
    assert not verify_ast_symbol_grounding(tmp_path, 1, 1, "value")


def test_encoding_cookie_and_crlf_are_supported(tmp_path: Path):
    target = tmp_path / "encoded.py"
    target.write_bytes("# coding: cp1252\r\nlabel = 'caf\xe9'\r\n".encode("cp1252"))
    assert verify_ast_symbol_grounding(target, 2, 2, "label")
    assert not verify_ast_symbol_grounding(target, 3, 3, "label")


def test_utf8_bom_and_no_final_newline_are_supported(tmp_path: Path):
    target = tmp_path / "bom.py"
    target.write_bytes("value = 1".encode("utf-8-sig"))
    assert verify_ast_symbol_grounding(target, 1, 1, "value")


def test_invalid_encoding_is_not_grounded(tmp_path: Path):
    target = tmp_path / "encoding.py"
    target.write_bytes(b"value = '\xff'\n")
    assert not verify_ast_symbol_grounding(target, 1, 1, "value")


def test_source_is_never_executed(tmp_path: Path):
    target = tmp_path / "dangerous.py"
    target.write_text("raise RuntimeError('must not execute')\nvalue = 1\n", encoding="utf-8")
    assert verify_ast_symbol_grounding(target, 2, 2, "value")


def test_read_failure_is_not_grounded(source_path: Path, monkeypatch: pytest.MonkeyPatch):
    def deny_read(*args, **kwargs):
        raise PermissionError("read denied")

    monkeypatch.setattr("antemortem.citations.tokenize.open", deny_read)
    assert not verify_ast_symbol_grounding(source_path, 1, 1, "calculate")


def test_run_module_exposes_same_helper():
    from antemortem.commands.run import verify_ast_symbol_grounding as run_helper

    assert run_helper is verify_ast_symbol_grounding


@pytest.mark.parametrize(
    ("source", "symbol"),
    [
        ("bucket[(index := 0)] = 7\n", "index"),
        ("bucket[[item for item in values]] = 7\n", "item"),
    ],
)
def test_subscript_expression_bindings_are_not_assignment_targets(
    tmp_path: Path, source: str, symbol: str
):
    target = tmp_path / "subscript.py"
    target.write_text(source, encoding="utf-8")
    assert not verify_ast_symbol_grounding(target, 1, 1, symbol)


@pytest.mark.parametrize("symbol", ["head", "middle", "tail"])
def test_nested_and_starred_targets_remain_grounded(tmp_path: Path, symbol: str):
    target = tmp_path / "unpacking.py"
    target.write_text("[head, (middle, *tail)] = values\n", encoding="utf-8")
    assert verify_ast_symbol_grounding(target, 1, 1, symbol)
