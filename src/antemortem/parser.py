# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Parse antemortem markdown documents into structured objects.

The parser is deliberately simple: YAML frontmatter via ``python-frontmatter``,
then string-based section extraction with a small set of heading anchors. We
avoid a full markdown AST parser because the template is fixed and
well-structured — regex is sufficient and keeps the dependency footprint small.

Reviewer P1 reinforced two robustness fixes:
- Section storage is a list[Section], not a dict keyed by heading text.
  Two sections sharing the same `##` title (e.g. an example doc with two
  ``## 2. Traps hypothesized``) used to silently overwrite each other in
  the dict — the second wins, the first vanishes.
- Trap-table cell splitter is escaped-pipe-aware. A trap hypothesis or
  notes column containing ``a \\| b`` used to split mid-cell.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import frontmatter

from antemortem.schema import AntemortemDocument, Frontmatter, Trap


class DocumentParseError(ValueError):
    """Raised when an antemortem document cannot be parsed."""


_HEADING_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Section:
    """One ``##``-level section in the document.

    Stored as a list so duplicate titles are preserved (the dict-keyed
    storage that preceded this silently dropped earlier sections when
    a later section shared the same heading text).
    """

    title: str
    body: str
    start_line: int


def _split_sections_list(markdown: str) -> list[Section]:
    """Return all ``##``-headed sections in document order.

    Duplicate titles are preserved — the consumer (``_find_section``)
    picks by keyword match against the first occurrence, so the
    semantics are unchanged for non-duplicate documents.
    """
    matches = list(_HEADING_RE.finditer(markdown))
    sections: list[Section] = []
    for i, match in enumerate(matches):
        title = match.group("title")
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        # Compute 1-indexed line number of the heading.
        start_line = markdown[: match.start()].count("\n") + 1
        sections.append(
            Section(
                title=title,
                body=markdown[start:end].strip(),
                start_line=start_line,
            )
        )
    return sections


def _split_sections(markdown: str) -> dict[str, str]:
    """Backward-compat dict view of the section list.

    First-occurrence semantics: when two sections share a heading, the
    earlier one wins (the dict-keyed callers that depend on this
    function were always reading the first match anyway). Direct callers
    that need duplicate-aware traversal should use
    ``_split_sections_list``.
    """
    out: dict[str, str] = {}
    for s in _split_sections_list(markdown):
        key = s.title.lower()
        if key not in out:  # preserve first-match (was last-wins pre-fix)
            out[key] = s.body
    return out


def _find_section(sections: dict[str, str], *keywords: str) -> str:
    """Return the first section whose heading contains all ``keywords``."""
    for title, body in sections.items():
        if all(keyword.lower() in title for keyword in keywords):
            return body
    return ""


def split_markdown_table_row(row: str) -> list[str]:
    """Split a Markdown table row, respecting backslash-escaped pipes.

    Reviewer P1: pre-fix the parser used ``row.strip().strip('|').split('|')``
    which breaks on cells containing escaped pipes. ``| a \\| b | c |``
    used to parse as 4 cells (``a \\``, `` b ``, `` c ``, ``-`` empty),
    not 2.

    Returns the list of cell strings with surrounding whitespace stripped
    and the leading/trailing pipe characters removed. Backslash-escaped
    pipes (``\\|``) become literal ``|`` in the cell text.
    """
    # Strip outer whitespace + leading/trailing pipe (mandatory in
    # well-formed Markdown table rows).
    s = row.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]

    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            buf.append("|")  # escaped pipe -> literal pipe in cell
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def _extract_spec(sections: dict[str, str]) -> str:
    """Pull the first meaningful paragraph of the change description."""
    body = _find_section(sections, "the change")
    if not body:
        return ""
    # Drop sub-headings like '### 1.1 Assumed invariants' -- we only want the
    # top paragraph describing the change itself.
    top = body.split("###", 1)[0].strip()
    return top


def _extract_files_to_read(sections: dict[str, str]) -> list[str]:
    """Pull the bullet-list file paths from the Recon protocol section."""
    # Use the full phrase "recon protocol" -- the Traps section title contains
    # "pre-recon" which would otherwise match first by insertion order.
    body = _find_section(sections, "recon protocol")
    if not body:
        return []
    files: list[str] = []
    # Paths live inside backticks under a 'Files handed to the model' bullet.
    for match in re.finditer(r"`([^`\n]+)`", body):
        token = match.group(1).strip()
        if not token:
            continue
        # Filter out placeholder patterns from the template.
        if token.startswith("<") and token.endswith(">"):
            continue
        # Only keep entries that look like file paths (have a dot or slash).
        if "/" in token or "\\" in token or "." in token:
            files.append(token.replace("\\", "/"))
    # Preserve first occurrence order while deduplicating.
    seen: set[str] = set()
    unique: list[str] = []
    for path in files:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


_TRAP_ROW_RE = re.compile(r"^\|\s*(\d+|t\d+)\s*\|", re.MULTILINE)


def _extract_traps(sections: dict[str, str]) -> list[Trap]:
    """Parse the pre-recon Traps table into structured rows."""
    body = _find_section(sections, "trap")
    if not body:
        return []

    traps: list[Trap] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = split_markdown_table_row(stripped)
        if len(cells) < 3:
            continue
        # Skip header and separator rows.
        first = cells[0].lower()
        if first in ("#", "id", "") or set(first) <= set("-: "):
            continue
        if "trap" in first and "description" in cells[1].lower():
            continue

        raw_id = cells[0]
        trap_id = raw_id if raw_id.lower().startswith("t") else f"t{raw_id}"

        # Template row with placeholders like '<description>' -- skip.
        hypothesis = cells[1]
        if hypothesis.startswith("<") and hypothesis.endswith(">"):
            continue
        if not hypothesis:
            continue

        trap_type = cells[2] if len(cells) > 2 else "trap"
        # Basic template: columns are id | trap | label | P | notes
        # Enhanced template: id | trap | type | P | ... | notes
        # In both, column index 2 is the type/label and the last non-empty cell
        # tends to be notes. We keep notes as the final cell.
        notes = cells[-1] if len(cells) > 3 else ""
        if notes and notes.startswith("<") and notes.endswith(">"):
            notes = ""

        # Normalize trap type to one of trap/worry/unknown when the cell
        # contains a slash or variation (e.g. "trap/worry/unknown" placeholder).
        normalized_type = trap_type.strip().lower()
        if "/" in normalized_type:
            normalized_type = normalized_type.split("/", 1)[0]
        if normalized_type not in ("trap", "worry", "unknown"):
            normalized_type = "trap"

        traps.append(
            Trap(
                id=trap_id,
                hypothesis=hypothesis,
                type=normalized_type,
                notes=notes,
            )
        )
    return traps


def parse_markdown(raw: str) -> AntemortemDocument:
    """Parse a full antemortem markdown string into an ``AntemortemDocument``."""
    post = frontmatter.loads(raw)
    meta = post.metadata or {}
    try:
        fm = Frontmatter.model_validate(meta)
    except Exception as exc:
        raise DocumentParseError(f"YAML frontmatter validation failed: {exc}") from exc

    body = post.content or ""
    sections = _split_sections(body)
    return AntemortemDocument(
        frontmatter=fm,
        spec=_extract_spec(sections),
        files_to_read=_extract_files_to_read(sections),
        traps=_extract_traps(sections),
        raw_markdown=raw,
    )


def parse_document(path: Path) -> AntemortemDocument:
    """Read and parse an antemortem document from disk."""
    if not path.exists() or not path.is_file():
        raise DocumentParseError(f"antemortem document not found: {path}")
    text = path.read_text(encoding="utf-8")
    return parse_markdown(text)
