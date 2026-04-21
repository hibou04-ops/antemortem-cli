"""Parser tests — use programmatically generated sample docs."""

from pathlib import Path

import pytest

from antemortem.parser import DocumentParseError, parse_document, parse_markdown


SAMPLE_BASIC = """---
name: test-feature
date: 2026-04-21
scope: change-local
reversibility: high
status: draft
template: basic
---

# Antemortem — test feature

## 1. The change

Add a new auth middleware that validates JWT tokens.

## 2. Traps hypothesized (pre-recon)

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | token expiry not handled | trap | 60% | from prior incident |
| 2 | race condition on refresh | worry | 30% | uncertain |
| 3 | missing audit log | unknown | 50% | no signal yet |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/auth/middleware.py`
  - `src/auth/token.py`
- **Time spent:** 15 minutes
- **Scope:** narrow

## 4. Findings (classification with citations)

Not yet populated.
"""


SAMPLE_ENHANCED = """---
name: migration
date: 2026-04-21
template: enhanced
status: draft
---

# Antemortem (enhanced) — migration

## 1. The change

Migrate user sessions from in-memory to Redis.

### 1.1 Assumed invariants (explicit)

- Invariant 1: sessions do not expire mid-request

## 2. Traps hypothesized (pre-recon) — calibrated

| # | trap | type | P(issue) | evidence strength | blast radius | reversibility | notes |
|---|------|------|----------|-------------------|--------------|---------------|-------|
| 1 | serialization break | trap | 70% | high | module | hard | pickle concern |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/session/store.py`
  - `src/session/serializer.py`
"""


def test_parse_basic_frontmatter():
    doc = parse_markdown(SAMPLE_BASIC)
    assert doc.frontmatter.name == "test-feature"
    assert doc.frontmatter.template == "basic"
    assert doc.frontmatter.date == "2026-04-21"


def test_parse_basic_spec():
    doc = parse_markdown(SAMPLE_BASIC)
    assert "JWT tokens" in doc.spec
    assert "## " not in doc.spec  # should be just the paragraph, no headings


def test_parse_basic_files_to_read():
    doc = parse_markdown(SAMPLE_BASIC)
    assert doc.files_to_read == ["src/auth/middleware.py", "src/auth/token.py"]


def test_parse_basic_traps():
    doc = parse_markdown(SAMPLE_BASIC)
    assert len(doc.traps) == 3
    ids = [t.id for t in doc.traps]
    assert ids == ["t1", "t2", "t3"]
    types = [t.type for t in doc.traps]
    assert types == ["trap", "worry", "unknown"]
    assert "token expiry" in doc.traps[0].hypothesis


def test_parse_basic_raw_markdown_preserved():
    doc = parse_markdown(SAMPLE_BASIC)
    assert doc.raw_markdown == SAMPLE_BASIC


def test_parse_enhanced():
    doc = parse_markdown(SAMPLE_ENHANCED)
    assert doc.frontmatter.template == "enhanced"
    assert "Redis" in doc.spec
    # Sub-heading '### 1.1' must not leak into spec.
    assert "1.1" not in doc.spec
    assert doc.files_to_read == ["src/session/store.py", "src/session/serializer.py"]
    assert len(doc.traps) == 1
    assert doc.traps[0].type == "trap"


def test_parse_document_from_disk(tmp_path: Path):
    doc_path = tmp_path / "sample.md"
    doc_path.write_text(SAMPLE_BASIC, encoding="utf-8")
    doc = parse_document(doc_path)
    assert doc.frontmatter.name == "test-feature"
    assert len(doc.traps) == 3


def test_parse_missing_file_raises(tmp_path: Path):
    with pytest.raises(DocumentParseError):
        parse_document(tmp_path / "does-not-exist.md")


def test_parse_missing_name_raises():
    bad = """---
date: 2026-04-21
---
# Antemortem

## 1. The change
x
"""
    with pytest.raises(DocumentParseError):
        parse_markdown(bad)


def test_parse_empty_sections_returns_empty_lists():
    minimal = """---
name: minimal
date: 2026-04-21
---

# Antemortem — minimal

## 1. The change

Short paragraph.

## 2. Traps hypothesized

No table.

## 3. Recon protocol

No files.
"""
    doc = parse_markdown(minimal)
    assert doc.spec.startswith("Short")
    assert doc.files_to_read == []
    assert doc.traps == []


def test_parse_skips_placeholder_rows():
    """Template rows like '<description>' should not become traps."""
    with_placeholder = """---
name: tmpl
date: 2026-04-21
---

# Antemortem

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | <description> | trap / worry / unknown | % | <why you suspect this> |
| 2 | real trap text | trap | 50% | real note |
"""
    doc = parse_markdown(with_placeholder)
    assert len(doc.traps) == 1
    assert doc.traps[0].hypothesis == "real trap text"
