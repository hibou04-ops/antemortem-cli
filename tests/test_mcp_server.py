# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Tests for the antemortem MCP server.

Two layers:
- Wiring contract: tools are registered with non-empty schemas.
- End-to-end: the underlying tool functions actually execute against a
  mocked provider, exercising _build_traps_table, run_classification,
  the critic pass, and the decision gate.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

mcp = pytest.importorskip("mcp")

from antemortem.schema import (
    AntemortemOutput,
    Classification,
    CriticResult,
    NewTrap,
)


@pytest.fixture(scope="module")
def mcp_app():
    from antemortem.mcp import mcp_app as app

    return app


@pytest.fixture(scope="module")
def tools(mcp_app):
    return asyncio.run(mcp_app.list_tools())


EXPECTED_TOOLS = {"scaffold", "run", "lint"}


def test_three_commands_registered(tools):
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS


def test_each_tool_has_description(tools):
    for tool in tools:
        assert tool.description, f"tool {tool.name!r} has no description"
        assert len(tool.description) > 50, (
            f"tool {tool.name!r} description is too short for agents to use"
        )


def test_each_tool_has_input_schema(tools):
    for tool in tools:
        assert tool.inputSchema is not None
        assert "properties" in tool.inputSchema
        assert tool.inputSchema["properties"], (
            f"tool {tool.name!r} declares no input properties"
        )


def test_scaffold_required_args(tools):
    scaffold = next(t for t in tools if t.name == "scaffold")
    required = set(scaffold.inputSchema.get("required", []))
    assert "name" in required


def test_run_required_args(tools):
    run = next(t for t in tools if t.name == "run")
    required = set(run.inputSchema.get("required", []))
    assert "document" in required


def test_lint_required_args(tools):
    lint = next(t for t in tools if t.name == "lint")
    required = set(lint.inputSchema.get("required", []))
    assert "document" in required


# ---------------------------------------------------------------------------
# End-to-end execution against a mocked provider.
# ---------------------------------------------------------------------------

_DOC = """---
name: feat
date: 2026-04-21
template: basic
---

# Antemortem — feat

## 1. The change

Refactor the auth flow.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | token expiry | trap | 60% | from incident |
| 2 | race on refresh | worry | 30% | uncertain |

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


def _fake_provider(first_pass_output, critic_results=None):
    """Return a MagicMock provider whose structured_complete returns the
    classification output on the first call and (optionally) the critic
    batch on the second."""
    provider = MagicMock()
    provider.name = "anthropic"
    provider.model = "mock-model"
    usage = {
        "input_tokens": 80,
        "output_tokens": 220,
        "cache_creation_input_tokens": 4300,
        "cache_read_input_tokens": 0,
    }
    if critic_results is None:
        provider.structured_complete.return_value = (first_pass_output, usage)
    else:
        # Second call returns critic batch — its schema is _CriticBatch
        # internal to antemortem.critic; emulate via SimpleNamespace.
        from types import SimpleNamespace
        critic_batch = SimpleNamespace(critic_results=critic_results)
        provider.structured_complete.side_effect = [
            (first_pass_output, usage),
            (critic_batch, usage),
        ]
    return provider


def test_mcp_run_executes_classification(tmp_path: Path, monkeypatch):
    """Direct call to the tool function — would have caught the
    `t.a_priori_chance` AttributeError in _build_traps_table."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    from antemortem.mcp.server import run as mcp_run

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
            Classification(id="t2", label="GHOST", citation="src/auth.py:10", note="n"),
        ],
    )
    fake = _fake_provider(output)
    with patch("antemortem.mcp.server.make_provider", return_value=fake):
        result = mcp_run(document=str(doc_path), repo=str(repo))

    assert "classifications" in result
    assert result["classifications"][0]["id"] == "t1"
    assert "decision" in result  # default no_decision=False


def test_mcp_run_with_critic_uses_correct_signature(tmp_path: Path, monkeypatch):
    """Direct call with critic=True — would have caught the
    run_critic_pass(provider, output, ...) positional kwargs mismatch."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    from antemortem.mcp.server import run as mcp_run

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
            Classification(id="t2", label="GHOST", citation="src/auth.py:10", note="n"),
        ],
    )
    critic = [
        CriticResult(
            finding_id="t1",
            status="WEAKENED",
            issues=["evidence is weak"],
            counterevidence=["refresh path covers it"],
            recommended_label="UNRESOLVED",
        ),
    ]
    fake = _fake_provider(output, critic_results=critic)
    with patch("antemortem.mcp.server.make_provider", return_value=fake):
        result = mcp_run(document=str(doc_path), repo=str(repo), critic=True)

    assert result.get("critic_summary", {}).get("ran") is True
    assert result["critic_summary"]["downgrades_applied"] == 1


def test_mcp_run_raises_when_api_key_missing(tmp_path: Path, monkeypatch):
    """Missing API key surfaces as RuntimeError, not silent failure."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    from antemortem.mcp.server import run as mcp_run

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        mcp_run(document=str(doc_path), repo=str(repo))


def test_mcp_run_rejects_unknown_provider(tmp_path: Path):
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")

    from antemortem.mcp.server import run as mcp_run

    with pytest.raises(ValueError, match="Unknown provider"):
        mcp_run(document=str(doc_path), provider="nonexistent")


def test_mcp_run_raises_on_unparseable_document(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "broken.md"
    doc_path.write_text("not a valid antemortem doc", encoding="utf-8")

    from antemortem.mcp.server import run as mcp_run

    with pytest.raises(ValueError, match="Cannot parse"):
        mcp_run(document=str(doc_path))
