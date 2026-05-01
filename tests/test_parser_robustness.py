# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Reviewer P1: parser robustness — escaped pipes + duplicate-heading
preservation.

Two issues:

1. ``_extract_traps`` used ``stripped.strip('|').split('|')`` which
   breaks on cells containing backslash-escaped pipes (``a \\| b``).
2. ``_split_sections`` returned a dict keyed by lowercased heading;
   duplicate ``##`` headings overwrote each other silently. Now stored
   as ``list[Section]`` with first-match-wins dict semantics for
   backward compat.
"""
from __future__ import annotations

from pathlib import Path

from antemortem.parser import (
    Section,
    _split_sections,
    _split_sections_list,
    parse_document,
    split_markdown_table_row,
)


# ---------------------------------------------------------------------------
# split_markdown_table_row.
# ---------------------------------------------------------------------------


def test_simple_row_splits_into_cells():
    cells = split_markdown_table_row("| t1 | hypothesis | trap | 60% | n |")
    assert cells == ["t1", "hypothesis", "trap", "60%", "n"]


def test_escaped_pipe_inside_cell_kept_as_literal():
    cells = split_markdown_table_row("| t1 | a \\| b is or | trap | 60% | n |")
    assert cells == ["t1", "a | b is or", "trap", "60%", "n"]


def test_multiple_escaped_pipes_in_one_cell():
    cells = split_markdown_table_row(r"| t1 | x \| y \| z | trap | 60% | n |")
    assert cells == ["t1", "x | y | z", "trap", "60%", "n"]


def test_row_without_outer_pipes():
    """Markdown technically allows tables without leading/trailing |."""
    cells = split_markdown_table_row(" t1 | hypothesis | trap ")
    assert cells == ["t1", "hypothesis", "trap"]


def test_empty_cells_preserved():
    cells = split_markdown_table_row("| t1 |  | trap |  | n |")
    assert cells == ["t1", "", "trap", "", "n"]


# ---------------------------------------------------------------------------
# _split_sections_list preserves duplicates.
# ---------------------------------------------------------------------------


def test_split_sections_list_preserves_duplicate_headings():
    md = (
        "## 1. The change\n\nfirst body\n\n"
        "## 1. The change\n\nsecond body — example\n\n"
        "## 2. Other\n\nother body\n"
    )
    sections = _split_sections_list(md)
    titles = [s.title for s in sections]
    assert titles == ["1. The change", "1. The change", "2. Other"]
    bodies = [s.body for s in sections]
    assert "first body" in bodies[0]
    assert "second body" in bodies[1]


def test_split_sections_list_records_start_line():
    md = "intro\n\n## A\n\nbody A\n\n## B\n\nbody B\n"
    sections = _split_sections_list(md)
    assert sections[0].title == "A"
    assert sections[0].start_line == 3
    assert sections[1].title == "B"
    assert sections[1].start_line == 7


# ---------------------------------------------------------------------------
# _split_sections (dict view) — first-match-wins.
# ---------------------------------------------------------------------------


def test_dict_view_first_match_wins():
    """Duplicate headings: the dict view returns the FIRST body, not
    the last (which would silently swap content under the same key)."""
    md = (
        "## Heading\n\nFIRST\n\n"
        "## Heading\n\nSECOND\n"
    )
    sections = _split_sections(md)
    assert "heading" in sections
    assert "FIRST" in sections["heading"]
    assert "SECOND" not in sections["heading"]


# ---------------------------------------------------------------------------
# Integration: a trap hypothesis with escaped pipes parses cleanly.
# ---------------------------------------------------------------------------


def test_parse_document_with_escaped_pipe_in_trap_hypothesis(tmp_path: Path):
    doc = (
        "---\nname: feat\ndate: 2026-04-21\ntemplate: basic\n---\n\n"
        "# Antemortem — feat\n\n"
        "## 1. The change\n\nx.\n\n"
        "## 2. Traps hypothesized\n\n"
        "| # | trap | label | P(issue) | notes |\n"
        "|---|------|-------|----------|-------|\n"
        "| 1 | request \\| response timing assumption | trap | 60% | n |\n\n"
        "## 3. Recon protocol\n\n"
        "- **Files handed to the model:**\n"
        "  - `src/auth.py`\n"
    )
    path = tmp_path / "feat.md"
    path.write_text(doc, encoding="utf-8")
    parsed = parse_document(path)
    assert len(parsed.traps) == 1
    trap = parsed.traps[0]
    # The hypothesis preserves the literal pipe rather than splitting.
    assert "|" in trap.hypothesis
    assert "request | response" in trap.hypothesis
