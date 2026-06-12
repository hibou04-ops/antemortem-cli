# MCP server: let your agent check its own work

`antemortem-cli` ships an [MCP](https://modelcontextprotocol.io) server,
`antemortem-mcp`, so a coding agent (Claude Code, Cursor, or any MCP
client) can run the antemortem discipline on its **own** planned change
*before* it edits code — and catch itself hallucinating a citation.

## Install

```bash
pip install "antemortem[mcp]"
```

## Tools exposed

The MCP server exposes **exactly three** tools, mirroring the pre-edit
phase of the CLI:

| MCP tool | Purpose |
|---|---|
| `scaffold` | Create an antemortem recon document from a template for the change about to be made. |
| `run` | Classify each trap against the actual repo files as `REAL` / `GHOST` / `NEW` / `UNRESOLVED`, every non-`UNRESOLVED` verdict carrying a `file:line` citation. |
| `lint` | Re-verify those citations offline against the disk. Zero LLM calls; catches the model citing evidence that does not resolve. |

> The CI-facing surface — gating, fabrication-rate metrics, and
> scorecards — is intentionally **not** exposed over MCP. Those run as
> the CLI (`antemortem gate`, `antemortem metrics`, `antemortem report`)
> in your pipeline, where a deterministic process exit code drives the
> build. The MCP surface is the agent-facing pre-edit loop only.

## Wire it into an MCP client

Paste this into `.mcp.json` (project-local) or
`claude_desktop_config.json` (the desktop client):

```jsonc
{
  "mcpServers": {
    "antemortem": {
      "command": "python",
      "args": ["-m", "antemortem.mcp"],
      "env": { "ANTHROPIC_API_KEY": "sk-ant-..." }
    }
  }
}
```

Use the API-key environment variable for whichever provider you run:
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GEMINI_API_KEY` /
`GOOGLE_API_KEY`. The local `ollama` provider needs no key.

## Transport

The server speaks **stdio** by default — what Claude Code and Cursor
expect:

```bash
python -m antemortem.mcp           # stdio (default)
python -m antemortem.mcp --http    # streamable-http transport
```

## Filesystem confinement

By default a tool caller may scaffold or read files anywhere the server
process can reach. To confine every path the agent passes to a single
root, set `ANTEMORTEM_WORKSPACE_ROOT`:

```jsonc
"env": {
  "ANTHROPIC_API_KEY": "sk-ant-...",
  "ANTEMORTEM_WORKSPACE_ROOT": "/abs/path/to/your/repo"
}
```

With it set, any path that resolves outside the root is rejected before
a file is read — so the agent cannot wander off the project tree.

## The point

The agent can no longer just *say* "I checked the repo." `run` produces
an artifact whose every claim points at a line on disk, and `lint`
decides whether that line actually backs the claim. Self-review you can
audit, not self-review you have to trust.

---

This page is part of the [`antemortem-cli`](../README.md) documentation set.
