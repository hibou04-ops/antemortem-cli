# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""MCP server exposing the antemortem-cli commands as agent-callable tools.

Run with:

    python -m antemortem.mcp           # stdio transport (Claude Code, Cursor)
    python -m antemortem.mcp --http    # streamable-http transport

Three tools mirror the CLI:

* ``scaffold``  — create an antemortem document from a template
* ``run``       — run LLM-assisted classification on an antemortem document
* ``lint``      — verify file:line citations and document structure

All three are intended for use *before* an agent edits code: scaffold the
recon document, run the classifier to expose REAL / GHOST / NEW / UNRESOLVED
risks, lint to catch hallucinated citations, then proceed with edits only
once the decision gate clears.
"""

from __future__ import annotations

from antemortem.mcp.server import mcp_app

__all__ = ["mcp_app"]
