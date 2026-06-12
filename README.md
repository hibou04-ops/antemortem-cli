# antemortem — does your AI agent actually read your code, or just sound like it?

**Your coding agent wrote a plan and swears it's safe against your repo. Prove it.**
`antemortem` makes the AI cite a real `file:line` for every claim, then **machine-checks each citation against the bytes on your disk — offline.** A fabricated citation makes the check fail. No prose to trust. A deterministic PASS / FAIL, with a hard **fabrication rate** number you can gate CI on.

[![CI](https://github.com/hibou04-ops/antemortem-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/hibou04-ops/antemortem-cli/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/antemortem?color=blue&label=pypi&cacheSeconds=3600)](https://pypi.org/project/antemortem/)
[![Python](https://img.shields.io/pypi/pyversions/antemortem?cacheSeconds=3600)](https://pypi.org/project/antemortem/)
[![License](https://img.shields.io/pypi/l/antemortem?color=blue&cacheSeconds=3600)](LICENSE)
[![MCP server](https://img.shields.io/badge/MCP-server-blueviolet?cacheSeconds=3600)](#1-the-hero-your-agent-runs-it-on-itself-mcp--ci)

> **AI code review · LLM hallucination check · verify AI citations · pre-merge AI plan review · AI agent guardrails · Claude Code / Cursor / Copilot hook · MCP server · GitHub Action**

README family: [English](README.md) · [한국어](README_KR.md) · [Easy start](EASY_README.md) · [쉬운 한국어](EASY_README_KR.md) · Deep docs: [`docs/`](docs/) · [Claim ledger](docs/claim_ledger.md) ([한국어](docs/claim_ledger_kr.md))

```bash
pip install antemortem
```

## Quick start

```bash
pip install antemortem
export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY / GEMINI_API_KEY; Ollama needs no key

antemortem init   my-feature                          # scaffold the recon doc
antemortem doctor my-feature.md --repo .              # preflight: no API call
antemortem run    my-feature.md --repo .              # one call → classifications + citations
antemortem lint   my-feature.md --repo .              # re-verify every citation offline
antemortem gate   my-feature.md --repo .              # enforce the decision policy in CI
```

No key to try it? Jump to [Try it in 30 seconds](#try-it-in-30-seconds--no-api-key) for the offline demo.

## Table of Contents

- [The problem, in one screen](#the-problem-in-one-screen)
- [The headline: a hard fabrication-rate number](#the-headline-a-hard-fabrication-rate-number)
- [The hero: your agent runs it on itself (MCP + CI)](#1-the-hero-your-agent-runs-it-on-itself-mcp--ci)
- [Try it in 30 seconds — no API key](#try-it-in-30-seconds--no-api-key)
- [Why this works — the two ideas](#why-this-works--the-two-ideas-this-is-the-word-antemortem)
- [The full loop (with an API key)](#the-full-loop-with-an-api-key)
- [Multi-provider — including local, keyless Ollama](#multi-provider--including-local-keyless-ollama)
- [When NOT to use it](#when-not-to-use-it)

---

## The problem, in one screen

In 2026 your agent — Claude Code, Cursor, Copilot, Aider — writes the plan and the patch, then tells you, confidently, that it's safe against your existing code. You have **no fast way to check whether it actually read your repo or just hallucinated a reassuring answer.**

LLMs are fluent. Fluency is not evidence. An agent will cite `auth/middleware.py:48` for a claim that line 48 doesn't support — or for a line that doesn't exist. You find out at runtime.

**antemortem is the gate that catches that.** It forces the model to ground every verdict in a real `file:line`, then re-reads each cited line **offline against the disk**. The output isn't prose you have to believe — it's a machine-checkable **PASS / FAIL** plus a **fabrication rate**:

```text
trap t1: "refresh path leaves the old session cookie live"
  model says: REAL   cite auth/middleware.py:45-52
  antemortem lint → lines 45-52 exist, evidence hash matches disk   ✓ VERIFIED

trap t2: "race on concurrent refresh"
  model says: GHOST  cite auth/token.py:72
  antemortem lint → file has 60 lines; line 72 does not exist       ✗ FABRICATED → exit 1
```

If the agent invented a citation, the second case is exactly what you see. The lie does not merge.

---

## The headline: a hard fabrication-rate number

`antemortem metrics` answers exactly one question — *is the model citing real evidence?* — and prints the number that proves it. Point it at a run artifact; it reports verified vs fabricated vs unresolved citations and a **fabrication rate**, then fails CI when that rate is too high:

```bash
# How often did the model hallucinate its own evidence?
antemortem metrics antemortem/feat.json --repo .
#   Citations: verified=7, fabricated=1, unresolved=2, cited=8, total=10
#   Fabrication rate: 12.5% of cited
#   Status: FAIL (fabricated citations present)

# Zero tolerance in CI — any fabricated citation fails the job (exit 4):
antemortem metrics antemortem/feat.json --repo . --fail-over 0 --format json
```

`--format json` emits a stable `antemortem-citation-metrics-v1` summary; `--fail-over <rate>` exits `4` (policy gate) when `fabricated / cited` exceeds your threshold. This is the LLM-hallucination check, reduced to one auditable percentage.

Need a shareable artifact instead of a console line? `antemortem report` renders the same run into a single-file Markdown or HTML scorecard — decision verdict, per-trap table, citation-verification status — self-contained (HTML inlines its own CSS) so you can attach it to a PR or publish it as a CI artifact:

```bash
antemortem report antemortem/feat.json --repo . --format html --out scorecard.html
```

---

## 1. The hero: your agent runs it on itself (MCP + CI)

### Wire it into your coding agent (MCP server)

`antemortem-mcp` is a [Model Context Protocol](https://modelcontextprotocol.io) server. Plug it into Claude Code (or any MCP client) and your agent gains three tools it can call on its **own** output before asking you to merge:

| MCP tool | What the agent does with it |
|---|---|
| `scaffold` | Opens a recon doc for the change it's about to make. |
| `run` | Classifies each risk against the **actual repo files** as `REAL` / `GHOST` / `NEW` / `UNRESOLVED`, every non-`UNRESOLVED` verdict carrying a `file:line` citation. |
| `lint` | **Re-verifies those citations offline against the disk.** Zero LLM calls. Catches the model hallucinating its own evidence. |

The MCP server exposes exactly these three tools (`scaffold`, `run`, `lint`). The CI-facing surface — gating, fabrication metrics, scorecards — runs as the CLI in your pipeline, not as MCP tools. One paste into `.mcp.json` (or `claude_desktop_config.json` for the desktop client):

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

```bash
pip install "antemortem[mcp]"
```

The server speaks stdio by default — what Claude Code expects. Need network transport? `python -m antemortem.mcp --http`. Confine the agent's filesystem reach with `ANTEMORTEM_WORKSPACE_ROOT`, so every path it passes must resolve under one root. Now the agent can't just *say* "I checked the repo" — it produces an artifact whose every claim points at a line on disk, and `lint` decides whether that line backs the claim. **Self-review you can audit, not self-review you have to trust.** Full setup in [`docs/MCP.md`](docs/MCP.md).

### Block the PR in CI — one `uses:` step

Because antemortem ships a composite **GitHub Action** (`action.yml` at the repo root), the whole gate is one step — no glue, no install script. It installs antemortem from PyPI, runs the offline `lint` + decision gate, and fails the job on a blocked decision or a fabricated citation:

```yaml
# .github/workflows/antemortem.yml
name: antemortem gate
on: [pull_request]
jobs:
  recon-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hibou04-ops/antemortem-cli@v0.11.0
        with:
          document: antemortem/my-feature.md
          repo: .
          allow: SAFE_TO_PROCEED,PROCEED_WITH_GUARDS
```

The action's JSON summary (`schema: antemortem-gate-v1`) carries the verdict, decision, and fabricated-citation metrics, exposed as a step `summary` output for downstream steps. Prefer the raw CLI? The same gate is one shell line:

```yaml
      - run: pip install antemortem
      # Re-verify every citation against this checkout, then enforce the policy.
      - run: antemortem gate antemortem/my-feature.md --repo .
```

`antemortem gate` runs the offline `lint` first (citations + evidence hashes against disk), then enforces a **decision allowlist**. The four labels are deterministic — same artifact in, same verdict out, no model call:

| Decision | Meaning |
|---|---|
| `SAFE_TO_PROCEED` | No real risks remain. |
| `PROCEED_WITH_GUARDS` | Real risks exist, each has a remediation. |
| `NEEDS_MORE_EVIDENCE` | Too much unresolved, or citations don't hold. |
| `DO_NOT_PROCEED` | A high-severity risk with no mitigation. |

Default allowlist is `SAFE_TO_PROCEED,PROCEED_WITH_GUARDS`. Exit codes are stable: `0` pass · `1` validation/citation failure · `2` usage error · `3` provider failure · `4` policy gate blocked. CI branches on the exit code — it never reads prose. Full reference in [`docs/GITHUB_ACTION.md`](docs/GITHUB_ACTION.md).

### Gate the patch the agent *actually* wrote

Don't trust a hand-listed file scope — derive it from the diff. `antemortem run --diff <ref>` reads the changed files straight from a git diff and audits exactly that patch:

```bash
antemortem run antemortem/my-feature.md --repo . --diff origin/main
antemortem gate antemortem/my-feature.md --repo . --format json
```

`--diff` accepts `staged`, `working`, or any git ref/range (`HEAD~1`, `origin/main`, `a..b`); the changed files are merged into the recon scope. So the gate covers the agent's *real* changes, not just the ones it chose to mention.

---

## "Just ask the agent to review it" — and why that loses

The free competitor is zero-friction: tell your agent *"review this plan against the repo."* It will. It'll sound thorough. An AI grading its own homework with no answer key writes whatever sounds right. Here's the gap antemortem closes — and how it differs from a post-diff PR-review bot (CodeRabbit, Copilot review, etc.):

| | Ask the agent to review it | PR-review bots (CodeRabbit, etc.) | **antemortem** |
|---|:-:|:-:|:-:|
| When it runs | chat, ad-hoc | **after** the diff exists | **before** the diff — on the plan |
| Who frames the risk list | the agent (rubber-stamps) | the bot | **you do, before it sees code** |
| Every claim cites `file:line` | no | sometimes | **yes (schema-enforced)** |
| Citations re-verified on disk | no | no | **yes (`lint`, offline, deterministic)** |
| Catches a *fabricated* citation | no | no | **yes (the run fails)** |
| Hard fabrication-rate number | no | no | **yes (`metrics`, gate on it)** |
| Machine pass/fail a PR can gate on | no | partial | **yes (stable exit codes)** |
| Persistent, re-checkable artifact | no (a chat message) | review comments | **yes (markdown + JSON + scorecard)** |

That answer key is `antemortem` — checked by a program, not by the agent's own confidence.

---

## Try it in 30 seconds — no API key

The bundled demo replays a real recon from stored output, so **no key and no network** are needed. The `lint` at the end is the live offline check:

```bash
git clone https://github.com/hibou04-ops/antemortem-cli.git
cd antemortem-cli && pip install -e ".[mcp]"

# 4 traps → REAL / GHOST / NEW / UNRESOLVED → a decision (pre-recorded, offline)
PYTHONIOENCODING=utf-8 python examples/demo_replay.py

# now machine-verify every file:line and evidence hash against disk
antemortem lint examples/demo_antemortem.md --repo .

# ...and reduce it to one fabrication-rate number
antemortem metrics examples/demo_antemortem.json --repo .
```

`lint` exits `0` if every citation checks out on disk, `1` if any is fabricated or stale. That single exit code is the whole product: a deterministic, offline answer to *"did the AI lie about the codebase?"*

---

## Why this works — the two ideas (this is the word "antemortem")

A *post*-mortem asks why something already failed. **An antemortem runs the autopsy before the patient — your change — is even born:** it interrogates an AI's plan against the real code *before* the first keystroke. That word is the whole method, and two mechanisms make the review impossible to rubber-stamp:

1. **Anchoring defense.** *You* enumerate the risks ("traps") **before the model sees the code.** The model never frames your risk list, so it can't quietly agree with its own framing and call it review. It has to take a position on *your* hypotheses, against *your* file scope.
2. **Hallucination-proof review.** Every non-`UNRESOLVED` verdict is a machine-verifiable disk citation, and a **deterministic offline lint fails the run if a citation is fabricated.** When the artifact carries an `evidence_hash` or snippet, lint also confirms the cited *text* hasn't drifted. The model's confidence is irrelevant — only the disk decides.

| Label | Meaning | Evidence required |
|---|---|---|
| `REAL` | The code confirms the risk. | `file:line` where it surfaces |
| `GHOST` | The code disproves it (already handled). | `file:line` that contradicts it |
| `NEW` | A risk the model found that you missed. | `file:line` of the raising code |
| `UNRESOLVED` | No evidence either way. Honest, not a failure. | none (explanation required) |

No mainstream tool turns LLM reconnaissance into a lint-able, gate-able CI artifact like this. The full trust model — what it verifies and what it deliberately does not — is in [`docs/trust_model.md`](docs/trust_model.md) ([한국어](docs/trust_model_kr.md)).

---

## The full loop (with an API key)

```bash
export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY / GEMINI_API_KEY / GOOGLE_API_KEY; Ollama needs no key

antemortem init    my-feature                          # scaffold the recon doc
#   edit antemortem/my-feature.md:
#     § Spec   — the change   § Traps — YOUR risk hypotheses   § Files — the scope
antemortem doctor  antemortem/my-feature.md --repo .   # preflight: no API call
antemortem run     antemortem/my-feature.md --repo .   # one call → classifications + citations
antemortem lint    antemortem/my-feature.md --repo .   # re-verify every citation offline
antemortem gate    antemortem/my-feature.md --repo .   # enforce the decision policy
antemortem metrics antemortem/my-feature.json --repo . # fabrication-rate number
antemortem report  antemortem/my-feature.json --repo . --format html --out scorecard.html
```

That is the full command surface — **9 commands**: `init`, `doctor`, `run`, `lint`, `evidence`, `gate`, `eval`, `metrics`, `report`. `evidence` fills/checks evidence hashes (no provider call), `eval` scores offline golden cases, and `--strict-evidence` on `lint` requires the cited *text*, not just the line range, to be unchanged.

---

## Multi-provider — including local, keyless Ollama

The discipline is vendor-neutral; the LLM is the only pluggable seam. First-class adapters ship for **`anthropic`, `openai`, `gemini`, and `ollama`** (local, keyless inference via a running daemon), plus any **OpenAI-compatible endpoint** (Azure, Groq, Together, OpenRouter) via `--provider openai --base-url <url>`:

```bash
antemortem run antemortem/feat.md --repo . --provider ollama          # local, no API key
antemortem run antemortem/feat.md --repo . --provider openai --base-url https://...  # compatible endpoint
```

Every adapter uses the provider's native structured-output path and validates the result against the same Pydantic schema — no client-side JSON regex anywhere. The CLI stays model-agnostic; pass `--model` to pin any model. Local and partially-compatible endpoints vary in structured-output fidelity, so `lint` stays mandatory there — which is the point: the disk check doesn't trust the model, regardless of vendor. The full capability matrix is in [`docs/provider_compatibility.md`](docs/provider_compatibility.md).

---

## When NOT to use it

Skip antemortem for trivial changes (typo, version bump), exploratory spikes with no spec yet, and hot-fixes where speed beats discipline. It validates your *plan against existing code* — it doesn't catch runtime bugs that live outside the files. It's a screening gate that runs **before** code review, tests, and design review, where changing direction is cheapest — not a replacement for them. Where antemortem sits relative to the rest of the toolkit is mapped in [`docs/toolkit_positioning.md`](docs/toolkit_positioning.md) ([한국어](docs/toolkit_positioning_kr.md)).

---

Built on real engineering: an offline test suite (`python -m pytest -q`, zero network in normal CI), an MCP server, four first-class providers, a deterministic decision gate, and a composite GitHub Action. The public claim surface is generated from source and self-checked — see [`docs/generated/claims.md`](docs/generated/claims.md) ([한국어](docs/generated/claims_kr.md)), validated by `python scripts/check_repo_consistency.py`.

```bash
pip install "antemortem[mcp]"      # MCP server + CLI
pip install antemortem             # CLI only
pip install "antemortem[ollama]"   # add local Ollama support
```

Deep dives in [`docs/`](docs/): CLI reference & exit codes · trust model · GitHub Action · MCP setup · schema (`src/antemortem/schema.py`) · decision rules (`src/antemortem/decision.py`). Methodology origin: [Antemortem](https://github.com/hibou04-ops/Antemortem).

**Same idea, other surfaces** (the [Hibou04 toolkit](https://github.com/hibou04-ops) — a verification gate where AI workflows skip one): [omegaprompt](https://github.com/hibou04-ops/omegaprompt) gates an overfit *prompt* · [omega-lock](https://github.com/hibou04-ops/omega-lock) gates an optimizer's *winning score* on held-out data.

License: Apache 2.0. © 2026 Kyunghoon Gwak.
