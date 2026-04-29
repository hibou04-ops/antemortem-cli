# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Smoke tests for the antemortem MCP server.

Verifies that all three commands are registered as MCP tools and that
their generated JSON schemas reflect the documented argument shapes.
Tool execution against live LLMs is not covered here; this layer is
exercised purely for the wiring contract.
"""

from __future__ import annotations

import asyncio

import pytest

mcp = pytest.importorskip("mcp")


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
