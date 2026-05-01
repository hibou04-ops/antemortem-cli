# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Reviewer P0: MCP `run` must apply the same FileSafetyConfig as CLI.

Pre-fix the MCP path called ``read_text()`` directly — agents could
list ``.env``, secrets, SSH keys, or arbitrary 200MB files in the
Recon protocol and the loader would happily ship them through the
provider boundary. CLI's ``run`` already applied deny-globs / .gitignore /
max-bytes / secret-redaction; MCP did not.

Post-fix MCP imports ``load_files_for_recon`` and accepts the same
safety kwargs (``max_file_bytes``, ``deny_glob``, ``respect_gitignore``,
``redact_secrets``) plus a grounding gate that refuses to run the
provider with zero files loaded.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

mcp = pytest.importorskip("mcp")

from antemortem.schema import AntemortemOutput, Classification


_DOC_TEMPLATE = """---
name: feat
date: 2026-04-21
template: basic
---

# Antemortem — feat

## 1. The change

Refactor.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | token expiry | trap | 60% | n |

## 3. Recon protocol

- **Files handed to the model:**
{files_md}
"""


def _doc_for(files: list[str]) -> str:
    body = "\n".join(f"  - `{f}`" for f in files)
    return _DOC_TEMPLATE.format(files_md=body)


def _provider_returning(output: AntemortemOutput) -> MagicMock:
    provider = MagicMock()
    provider.name = "anthropic"
    provider.model = "mock-model"
    provider.structured_complete.return_value = (output, {
        "input_tokens": 10,
        "output_tokens": 20,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    })
    return provider


def _classification(trap_id: str = "t1") -> AntemortemOutput:
    return AntemortemOutput(
        classifications=[
            Classification(id=trap_id, label="REAL", citation="src/auth.py:5", note="n"),
        ],
    )


# ---------------------------------------------------------------------------
# Default deny-globs MUST be active on the MCP path.
# ---------------------------------------------------------------------------


def test_mcp_run_skips_dotenv_by_default(tmp_path: Path, monkeypatch):
    """The smoking-gun scenario: agent lists .env in the Recon section.
    CLI silently skips with a deny-glob warning. Pre-fix MCP shipped it.
    Post-fix MCP must skip it the same way."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("SECRET=pizza", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text("\n".join(f"l{i}" for i in range(20)), encoding="utf-8")

    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_doc_for([".env", "src/auth.py"]), encoding="utf-8")

    from antemortem.mcp.server import run as mcp_run

    fake = _provider_returning(_classification())
    with patch("antemortem.mcp.server.make_provider", return_value=fake):
        result = mcp_run(document=str(doc_path), repo=str(repo))

    # Provider call happened (auth.py was loaded), but .env was held back.
    args, kwargs = fake.structured_complete.call_args
    sent_user_message = kwargs.get("user_message") or (args[1] if len(args) > 1 else "")
    assert "SECRET=pizza" not in sent_user_message
    warnings = result.get("repo_load_warnings", [])
    assert any(".env" in w for w in warnings)


def test_mcp_run_respects_gitignore(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("private/\n", encoding="utf-8")
    (repo / "private").mkdir()
    (repo / "private" / "notes.txt").write_text("internal", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text("\n".join(f"l{i}" for i in range(20)), encoding="utf-8")

    doc_path = tmp_path / "feat.md"
    doc_path.write_text(
        _doc_for(["private/notes.txt", "src/auth.py"]),
        encoding="utf-8",
    )

    from antemortem.mcp.server import run as mcp_run

    fake = _provider_returning(_classification())
    with patch("antemortem.mcp.server.make_provider", return_value=fake):
        result = mcp_run(document=str(doc_path), repo=str(repo))

    warnings = result.get("repo_load_warnings", [])
    assert any("private/notes.txt" in w for w in warnings)


def test_mcp_run_skips_file_over_max_bytes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "huge.py").write_text("x" * 1000, encoding="utf-8")
    (repo / "small.py").write_text("y", encoding="utf-8")

    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_doc_for(["huge.py", "small.py"]), encoding="utf-8")

    from antemortem.mcp.server import run as mcp_run

    fake = _provider_returning(_classification())
    with patch("antemortem.mcp.server.make_provider", return_value=fake):
        result = mcp_run(
            document=str(doc_path), repo=str(repo),
            max_file_bytes=100,  # huge.py is 1000 bytes -> skipped
        )

    warnings = result.get("repo_load_warnings", [])
    assert any("huge.py" in w for w in warnings)


# ---------------------------------------------------------------------------
# Grounding gate: zero files loaded must NOT call the provider.
# ---------------------------------------------------------------------------


def test_mcp_run_refuses_when_no_files_loaded(tmp_path: Path, monkeypatch):
    """Agent lists a non-existent file. CLI exits with an error message;
    pre-fix MCP just called the provider with files=[] which produced
    a speculative review with no grounding."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    repo = tmp_path / "repo"
    repo.mkdir()

    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_doc_for(["does/not/exist.py"]), encoding="utf-8")

    from antemortem.mcp.server import run as mcp_run

    fake = _provider_returning(_classification())
    with patch("antemortem.mcp.server.make_provider", return_value=fake):
        with pytest.raises(RuntimeError, match="No readable files"):
            mcp_run(document=str(doc_path), repo=str(repo))
    # Provider was never called:
    fake.structured_complete.assert_not_called()


def test_mcp_run_refuses_when_all_files_denied_by_glob(tmp_path: Path, monkeypatch):
    """Even if files exist, a glob that denies all of them should not
    proceed to provider call."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("SECRET=pizza", encoding="utf-8")

    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_doc_for([".env"]), encoding="utf-8")

    from antemortem.mcp.server import run as mcp_run

    fake = _provider_returning(_classification())
    with patch("antemortem.mcp.server.make_provider", return_value=fake):
        with pytest.raises(RuntimeError, match="No readable files"):
            mcp_run(document=str(doc_path), repo=str(repo))
    fake.structured_complete.assert_not_called()


# ---------------------------------------------------------------------------
# MCP tool schema exposes the new safety kwargs.
# ---------------------------------------------------------------------------


def test_mcp_run_schema_exposes_safety_kwargs(tools):
    run = next(t for t in tools if t.name == "run")
    properties = run.inputSchema["properties"]
    for kwarg in (
        "max_file_bytes",
        "deny_glob",
        "respect_gitignore",
        "redact_secrets",
    ):
        assert kwarg in properties, (
            f"MCP run signature missing {kwarg!r} — agents can't opt "
            "into the same safety controls the CLI exposes."
        )


@pytest.fixture(scope="module")
def tools():
    """Re-fixture for this file (test_mcp_server.py's tools fixture is
    module-scoped)."""
    import asyncio
    from antemortem.mcp import mcp_app
    return asyncio.run(mcp_app.list_tools())
