# antemortem-cli

Antemortem checks whether the risks in your implementation plan are `REAL`, `GHOST`, `NEW`, or `UNRESOLVED` before you write the diff. You write the spec, traps, and repo files to inspect; the CLI reads only those files, asks a provider for schema-constrained output, and requires disk-verifiable `file:line` citations for grounded claims. `lint` then re-checks schema, citations, and evidence bindings against the repository.

[![CI](https://github.com/hibou04-ops/antemortem-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/hibou04-ops/antemortem-cli/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![PyPI](https://img.shields.io/badge/pypi-0.10.2-blue.svg)](https://pypi.org/project/antemortem/)
[![Tests](https://img.shields.io/badge/tests-offline%20CI-brightgreen.svg)](https://github.com/hibou04-ops/antemortem-cli/tree/v0.10.2/tests/)
[![Providers](https://img.shields.io/badge/providers-anthropic%20%7C%20openai%20%7C%20gemini%20%7C%20openai--compatible-informational.svg)](#provider-support)
[![Methodology](https://img.shields.io/badge/methodology-Antemortem-blueviolet.svg)](https://github.com/hibou04-ops/Antemortem)

**Use it when**

- before risky refactors
- before agent-generated patches
- before merging implementation plans
- before CI gates on large changes

**Trust loop**

- `doctor`: preview what will be parsed, read, and sent before any provider call.
- `run`: produce a structured recon artifact with `REAL` / `GHOST` / `NEW` / `UNRESOLVED` classifications.
- `lint`: verify schema, citations, path bounds, and evidence hashes/snippets against disk.
- `evidence`: inspect or fill missing local evidence hashes without a provider call.
- `eval`: measure the harness against committed offline golden cases.
- `gate`: enforce the decision policy in CI.

Ordinary AI code review starts from a diff or a chat prompt. Antemortem starts from your pre-diff plan, makes you name traps before the model sees code, and treats ungrounded output as invalid rather than persuasive.

The CLI has seven commands: `init` / `doctor` / `run` / `lint` / `evidence` / `gate` / `eval`.

```bash
pip install antemortem
```

> **Current release: v0.10.2** — public README claims are checked against source of truth by `python scripts/check_repo_consistency.py`.

Generated source-of-truth claims: [English](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/generated/claims.md) · [Korean](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/generated/claims_kr.md).

Trust model: [English](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/trust_model.md) · [Korean](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/trust_model_kr.md).

Toolkit positioning: [English](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/toolkit_positioning.md) · [Korean](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/toolkit_positioning_kr.md).

Claim ledger: [English](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/claim_ledger.md) · [Korean](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/claim_ledger_kr.md).

CLI examples: [English](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/examples.md) · [Korean](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/examples_kr.md).

Provider support: Anthropic / Claude, OpenAI, Gemini, and OpenAI-compatible endpoints that support the structured-output `parse` path. See [Provider compatibility caveats](#provider-compatibility-caveats) before trusting local or partially compatible endpoints.

**MCP server.** This package also exposes `init`, `run`, `lint`, and `gate` as agent-callable MCP tools. Run `pip install "antemortem[mcp]"` then `python -m antemortem.mcp` (stdio, default for Claude Code) or `python -m antemortem.mcp --http`. See [AGENT_TRIGGERS.md scenario 1](https://github.com/hibou04-ops/omegaprompt/blob/main/AGENT_TRIGGERS.md#scenario-1--pre-implementation-reconnaissance) for when an agent should fire these.

---

## Demo (60s)

https://github.com/user-attachments/assets/7ccb714e-2162-4933-aee0-64855aa58f97

> 60-second walkthrough of `examples/demo_recon.py`: 4 traps hypothesized → REAL / GHOST / NEW / UNRESOLVED classifications with `file:line` citations → `Decision: PROCEED_WITH_GUARDS` → `lint` re-verifies every citation against disk → four-level decision-gate enum. Real `antemortem lint` output, paced for readability. Reproducible with `PYTHONIOENCODING=utf-8 python examples/demo_replay.py`.

This replay contract is checked by `tests/test_demo_replay.py`: the test runs the README command without API keys and verifies the labels, final decision, and lint verification against `examples/_demo_output.txt`.

---

## Quick start

### 0. Smoke test — deterministic replay (no API)

```bash
git clone https://github.com/hibou04-ops/antemortem-cli.git
cd antemortem-cli && pip install -e .

# Replay the bundled demo (4 traps → REAL/GHOST/NEW/UNRESOLVED → decision gate)
PYTHONIOENCODING=utf-8 python examples/demo_replay.py

# Re-verify every file:line citation and any evidence binding against disk
antemortem lint examples/demo_antemortem.md --repo .
```

This uses pre-recorded LLM outputs — no API keys, no network. Useful for CI sanity, first-time exploration, and lint validation.

### 1. Real recon — your own change spec

Set an API key for any provider:

```bash
export ANTHROPIC_API_KEY=...      # or OPENAI_API_KEY, GEMINI_API_KEY, GOOGLE_API_KEY (free tier: https://aistudio.google.com/apikey)
```

Run the release-gate flow (`init` → `doctor` → `run` → `lint` → `gate`):

```bash
# Scaffold a doc — markdown + YAML frontmatter
antemortem init auth-refactor

# Edit antemortem/auth-refactor.md
#    Fill: § Spec (the change), § Traps hypothesized (your risk list), § Recon protocol (files to read)
#    The model never frames § Traps. That's the anchoring defense.

# 0. Preflight the doc — no API call, no network
antemortem doctor antemortem/auth-refactor.md --repo .

# 1. Run the recon — one API call, structured output
antemortem run antemortem/auth-refactor.md --repo .
# → writes antemortem/auth-refactor.json with classifications + citations

# 2. Lint — re-verify every citation and evidence hash against disk
antemortem lint antemortem/auth-refactor.md --repo .

# 3. Gate — fail unless lint passes and the decision is allowed
antemortem gate antemortem/auth-refactor.md --repo .
```

### 2. CI gate

```yaml
# .github/workflows/antemortem.yml
- run: antemortem gate antemortem/my-feature.md --repo .
```

### Exit codes

Stable exit codes are documented in [CLI Exit Codes](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/cli_exit_codes.md): `0` success, `1` validation failure, `2` usage/configuration error, `3` provider failure, `4` policy gate failure, and `70` reserved internal error.

---

## How is this different?

| Capability | antemortem-cli | Pre-mortem checklists | LLM "review my plan" prompts | Code review tools |
|---|:-:|:-:|:-:|:-:|
| Risk enumeration template | ✓ | ✓ | varies | ✗ |
| **You frame your traps first (anchoring defense)** | ✓ | sometimes | ✗ | n/a |
| **`file:line` citations on every claim** | ✓ | ✗ | ✗ | varies |
| **Lint re-verifies citations on disk** | ✓ | ✗ | ✗ | partial |
| Pydantic-enforced structured output | ✓ | ✗ | ✗ | ✗ |
| Four-level decision gate enum | ✓ | ✗ | ✗ | ✗ |
| Provider-agnostic (cloud + local) | ✓ | n/a | varies | varies |

> **Position**: `antemortem-cli` is **recon-first**, not code-review-first. It runs *before* you write the diff, when changing direction is less costly. PR review runs *after* the code exists — different discipline, different stage.

---

📖 **Want depth?** Full architecture, data contract, design decisions, validation, and FAQ for skeptics below.
👋 **Want simpler?** [EASY_README.md](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/EASY_README.md) (English) · [EASY_README_KR.md](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/EASY_README_KR.md)
🇰🇷 한국어 README: [README_KR.md](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/README_KR.md)

> **Methodology**: Implements the [Antemortem](https://github.com/hibou04-ops/Antemortem) seven-step protocol as a CLI/CI verification tool: scaffolding, preflight, classification, lint, evidence maintenance, benchmark eval, and gate. Related toolkit roles are documented in [Toolkit Positioning](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/toolkit_positioning.md).

---

## Table of Contents

- [Demo (60s)](#demo-60s)
- [The failure mode this solves](#the-failure-mode-this-solves)
- [How it compares](#how-it-compares)
- [Worked example: a real ghost trap](#worked-example-a-real-ghost-trap)
- [The seven commands](#the-seven-commands)
- [Provider support](#provider-support)
- [The data contract](#the-data-contract)
- [Architecture](#architecture)
- [Design decisions worth defending](#design-decisions-worth-defending)
- [What this is NOT](#what-this-is-not)
- [Cost & performance](#cost--performance)
- [Validation](#validation)
- [Benchmark-backed claims](#benchmark-backed-claims)
- [Toolkit positioning](#toolkit-positioning)
- [FAQ for skeptics](#faq-for-skeptics)
- [Prior art & credit](#prior-art--credit)
- [Status & roadmap](#status--roadmap)
- [Design principles, in one page](#design-principles-in-one-page)
- [Contributing](#contributing)
- [Citing](#citing)
- [License](#license)

---

## The failure mode this solves

Every nontrivial change starts the same way. You write a spec. You jot down a handful of things that might go wrong. You open a PR. Then for the next half-day, you discover:

1. Two of your "risks" were never real. The code already handles them.
2. One risk you never thought of is load-bearing. You find it at runtime.
3. The spec has a missing field. You invent it under pressure, mid-implementation.

This is not a skill issue. It is the shape of the task: **a plan written on paper cannot be stress-tested without reading the code.** Code review catches what is on the PR. Tests catch what you thought to test. Neither helps with mistakes you baked in before the first keystroke.

Antemortem is that stress test. You enumerate your own traps before the model sees any code (anchoring defense). You hand the plan and the implicated files to a capable LLM. For each trap, the model returns exactly one of:

| Label | What it means | Required evidence |
|---|---|---|
| `REAL` | The code confirms the risk. The change breaks or regresses unless mitigated. | `file:line` where the failure surfaces. |
| `GHOST` | The code contradicts the risk. The feared behavior doesn't happen, or an existing mitigation already handles it. | `file:line` that disproves the hypothesis. |
| `NEW` | A risk the model surfaced that wasn't on your list. | `file:line` of the raising code. |
| `UNRESOLVED` | No evidence in the provided files either way. Honest, not a failure. | `null` (but explanation required). |

Two guardrails turn this from *"ask Claude to review my plan"* into a discipline:

1. **You enumerate before the model sees the code.** The model never frames your risk list — you do. This kills anchoring at the source.
2. **Every non-UNRESOLVED classification carries a `file:line` citation.** The schema is Pydantic-enforced at the SDK boundary, and `antemortem lint` re-verifies every citation against disk. When artifacts carry `evidence_hash` or `evidence_snippet`, lint also verifies the cited text binding.

Without these two guardrails, you have traded one form of hand-waving for another. With them, the result is a mechanical screening step whose claims can be checked by schema validation, citation linting, and evidence binding.

---

## How it compares

Pre-implementation risk surfacing is not new. What `antemortem-cli` adds is the *discipline around the LLM call* — two guardrails (anchoring defense, citation verification) plus a deterministic decision gate, none of which are opinions you can wave away.

### Approach matrix

| Approach | What it catches | What it misses | What antemortem-cli adds |
|---|---|---|---|
| **Pre-mortem** (Klein, 2007) | Strategic framing risks — whether the project should exist. | Source-level specifics (no code is read). Solo use cases. | Change-level, source-code-grounded, solo, 15-min discharge. Pre-mortem *and* antemortem compose — they operate at different scopes. |
| **"Explain my plan" to an LLM** | Obvious fluency mistakes. | The LLM anchors on your framing and agrees. No citation. No disk check. Answers *"probably fine"* to everything. | Enumerate-before-show, `file:line` citations mandatory, `lint` re-verifies on disk. The degenerate case this tool exists to prevent. |
| **Code review on the PR** | Mistakes that survived into the diff. | Mistakes baked in *before* the first keystroke — the ones most expensive to fix. | Runs before the diff exists. Catches the category review cannot see. |
| **Tests** | Behavior deviations from expectation. | Mistaken expectations. | Validates the *plan* against the existing code, not the code against the plan. |
| **IDE-integrated planning** (Cursor, Claude Code, Aider) | Same-session, conversational guidance. | Plan lives in the chat; no artifact you can reread six months later. No mechanical citation check. | A persistent markdown + JSON artifact per change. Disk-verified citations. Four-level decision enum CI can gate on. |
| **GitHub Copilot Workspace / agentic coding** | Multi-step plan execution inside an agent. | Plan and execution intertwined. No mandatory citation discipline. No `lint` re-verification. | Discipline around the *planning* call, before any agent runs. Compose: agent reads the antemortem artifact as a constraint document. |
| **Static analysis / SAST** (Semgrep, CodeQL, Bandit) | Known anti-pattern fingerprints in existing code. | Risks specific to a *change you're about to make*. Plan-vs-code mismatches. | Pre-implementation, change-specific, plan-aware. SAST runs on the diff; antemortem runs on the spec before the diff. |
| **Linear / Jira / spec docs** | Strategic alignment, deadlines, ownership. | Code-level risk surfacing. No mechanical pass/fail. | Mechanical, machine-readable artifact (REAL/GHOST/NEW/UNRESOLVED) that links specs to source. |

### Capability matrix

| Capability | antemortem-cli | "Ask Claude/GPT" | Code review | Tests | Copilot Workspace | Cursor / Aider | SAST tools |
|---|---|---|---|---|---|---|---|
| **Anchoring defense** (you enumerate before LLM sees code) | ✅ (mandatory order) | ❌ | n/a | n/a | ❌ | ❌ | n/a |
| **Mandatory `file:line` citations** | ✅ (Pydantic-enforced) | ❌ | optional | n/a | ❌ | ❌ | ✅ (own format) |
| **Citation lint re-verifies on disk** | ✅ (`antemortem lint`) | ❌ | ❌ | n/a | ❌ | ❌ | ❌ (own engine, not cross-checked) |
| **Four-level decision enum** (`SAFE_TO_PROCEED` / `PROCEED_WITH_GUARDS` / `NEEDS_MORE_EVIDENCE` / `DO_NOT_PROCEED`) | ✅ | ❌ | ❌ | pass/fail | ❌ | ❌ | severity tiers |
| **Critic pass** (asymmetric: only downgrades) | ✅ (opt-in `--critic`) | ❌ | reviewer judgment | n/a | ❌ | ❌ | ❌ |
| **REAL / GHOST / NEW / UNRESOLVED labels** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Persistent artifact per change** | ✅ (markdown + JSON sibling) | ❌ (chat) | ✅ (PR) | ✅ (CI run) | ❌ (chat) | ❌ (chat) | ✅ (report) |
| **CI integration via decision enum** | ✅ (exit code on lint) | ❌ | ✅ (PR status) | ✅ | ❌ | ❌ | ✅ |
| **Multi-provider** (Anthropic / OpenAI / Gemini / OpenAI-compatible / local) | ✅ | depends | n/a | n/a | OpenAI-only | partial | n/a |
| **Vendor-neutral artifact** | ✅ | ❌ | n/a | n/a | ❌ | ❌ | n/a |
| **Cost per recon** | ~$0.04 (single-pass) / ~$0.08 (with critic) | varies | engineer time | engineer time | $20/mo Pro | $20/mo | $0–enterprise |
| **Time per recon** | 15 min (most of it: human writing traps) | 5–60 min | hours–days | minutes (CI) | continuous | continuous | minutes (CI) |
| **Tests** | Offline suite verified with `python -m pytest -q`; zero network in normal CI | n/a | n/a | n/a | n/a | n/a | varies |

### Where each shines

- **Pre-mortem** (Klein) — strategic / org-level alignment. Use *together* with antemortem-cli; they operate at different scopes.
- **Code review** — catches what the diff actually does. Antemortem catches what the diff *should not* do, before it exists.
- **Tests** — validate code against expectation. Antemortem validates *expectation* against existing code.
- **Cursor / Claude Code / Aider** — agentic coding inside an IDE. They write code; antemortem reviews the *plan* the code will be based on. Compose them: feed the antemortem artifact to the agent as a constraint.
- **SAST** (Semgrep, CodeQL, Bandit) — catches known anti-patterns *in code*. Antemortem catches change-specific risks *before code*. Different layer.
- **antemortem-cli** — pre-implementation, change-specific, source-grounded, citation-verified. The discipline that gives every other layer above better signal.

### Composition pattern

```bash
# 1. PRE-implementation — antemortem runs before any code is written
antemortem init my-feature
# (you write spec + traps + recon protocol)
antemortem doctor antemortem/my-feature.md --repo .
antemortem run antemortem/my-feature.md --repo .
antemortem lint antemortem/my-feature.md --repo .
antemortem gate antemortem/my-feature.md --repo .
# decision = SAFE_TO_PROCEED, PROCEED_WITH_GUARDS, NEEDS_MORE_EVIDENCE, or DO_NOT_PROCEED

# 2. IMPLEMENTATION — agent / pair-programming / manual
# (your favourite tool: Cursor, Claude Code, Aider, or your own hands)
# The agent reads antemortem/my-feature.json as a constraint document.

# 3. PR-time — code review + tests + SAST
git push  # → CI runs tests + Semgrep + CodeQL on the diff
# Reviewer checks the diff matches the antemortem's REAL findings + remediation.

# 4. POST-merge — observability / monitoring
# Compare runtime behaviour with what the antemortem predicted.
```

Each layer catches what the others can't. Antemortem-cli is the one that runs *before* anything else — that's the niche.

### When NOT to use antemortem-cli

Honest scope boundaries:

- **The change is trivial.** Renaming a variable, fixing a typo, bumping a dependency patch version. Recon overhead exceeds the benefit.
- **Exploratory / spike code.** When you're discovering the right approach, the spec doesn't exist yet. Use a notebook + iteration. Run antemortem before *productionising* the approach.
- **Hot-fix / incident response.** Speed matters more than discipline. Apply the patch, write the antemortem post-incident.
- **You're not the implementer.** Antemortem's anchoring defense depends on the human who'll write the code enumerating their own traps first. Hand-off recons lose half the value.
- **The codebase is too small.** If the repo is one file, traps surface in seconds without a tool. Once you cross ~10k LOC and multi-module, the citation discipline pays off.

### Toolkit boundary

`antemortem-cli` is the pre-implementation reconnaissance tool: it classifies implementation-plan risks before code changes and requires citation/evidence checks for its CLI artifact. Adjacent tools such as `omegaprompt`, `omega-lock`, `mini-omega-lock`, and `mini-antemortem-cli` have separate calibration, audit, or preflight roles. See [Toolkit Positioning](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/toolkit_positioning.md) for the neutral role map.

The tool is opinionated on one axis: **a citation the lint can't verify on disk is not evidence, regardless of how confident the model sounds.** Everything else flows from that.

---

## Worked example: a real ghost trap

The `omega_lock.audit` submodule was built using this CLI's methodology (case study: [`hibou04-ops/Antemortem/examples/omega-lock-audit.md`](https://github.com/hibou04-ops/Antemortem/blob/main/examples/omega-lock-audit.md)). Seven risks were on the initial list. The 15-minute recon returned:

```
Trap t1: WalkForward folds internally, so audit decorator double-counts eval cost.
    Label:    GHOST
    Citation: src/omega_lock/walk_forward.py:82
    Note:     evaluate() is called exactly once per params object — no loop, no fold.
              The feared O(n × folds) cost does not exist.
```

That one classification, with that one `file:line`, saved approximately **half an engineer-day**. The feared architecture rewrite was based on a wrong mental model.

Overall outcome:
- 1 ghost (trap t1 above)
- 3 risk downgrades (30–40% → 10–15%)
- 1 new requirement surfaced (`target_role` field, added to spec before implementation)
- P(full spec ships on time): **55–65% → 70–78%**
- Implementation: 1 engineer-day. 20 new tests passed on first run.

The post-implementation note honestly records what the recon *missed* — a Windows `cp949` terminal encoding issue that surfaced at runtime. Antemortems do not catch platform encoding issues. That admission is part of the case study; see [Limits in methodology.md](https://github.com/hibou04-ops/Antemortem/blob/main/docs/methodology.md#limits).

---

## The seven commands

### `antemortem init <name>`

Scaffolds a document from the official template. YAML frontmatter (`name`, `date`, `scope`, `reversibility`, `status`, `template`) plus a seven-section body. `--enhanced` swaps to the richer template: calibration dimensions (evidence strength, blast radius, reversibility), fine-grained classification subtypes (`REAL-structural`, `GHOST-mitigated`, `NEW-spec-gap`, …), an explicit skeptic pass on every REAL/NEW finding, and a decision-first output structure.

```bash
antemortem init my-feature                  # basic
antemortem init prod-migration --enhanced   # for high-stakes changes
```

Templates are vendored from [Antemortem](https://github.com/hibou04-ops/Antemortem) under Apache 2.0.

### `antemortem doctor <doc>`

Inspects a filled-in recon document before any provider call. It parses frontmatter and traps, applies the same file safety policy as `run`, computes the payload size, reports missing or excluded files, and exits with `READY`, `READY_WITH_WARNINGS`, or `NOT_READY`.
It writes no artifact unless `--json-output <path>` is passed.

```bash
antemortem doctor antemortem/my-feature.md --repo .
antemortem doctor antemortem/my-feature.md --repo . --json
antemortem doctor antemortem/my-feature.md --repo . --show-files --show-payload-preview
```

### `antemortem run <doc>`

Parses the document, extracts the spec + traps table + listed files, loads file contents from `--repo`, calls the configured provider with a frozen system prompt, and writes the classifications to a JSON audit artifact alongside the markdown (`<doc>.json`).

```bash
# Anthropic (default)
antemortem run antemortem/my-feature.md --repo .

# OpenAI
antemortem run antemortem/my-feature.md --repo . --provider openai

# Gemini
export GEMINI_API_KEY=...
antemortem run antemortem/my-feature.md --repo . \
  --provider gemini \
  --model gemini-2.5-flash

# OpenAI-compatible endpoint (local Ollama, Azure, Groq, etc.)
antemortem run antemortem/my-feature.md --repo . \
  --provider openai \
  --model llama3.1:70b \
  --base-url http://localhost:11434/v1

# With the optional second-pass critic (~2x API cost, high-stakes only)
antemortem run antemortem/my-feature.md --repo . --critic
```

**Optional second pass — `--critic`.** The critic re-reads every REAL and NEW finding against the same evidence and returns exactly one of `CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE`. The dedicated ~1.5k-token critic prompt is explicitly asymmetric: the critic can only downgrade. `WEAKENED` → `UNRESOLVED`; `CONTRADICTED` → `GHOST` or `UNRESOLVED` based on counterevidence; `DUPLICATE` → dropped; `CONFIRMED` → unchanged. This makes the second pass a conservative review filter, not a source of new findings. Off by default. Enable on changes where a false REAL is expensive.

**Four-level decision gate (default on, `--no-decision` to skip).** Every run emits exactly one of:

| Decision | Fires when |
|---|---|
| `SAFE_TO_PROCEED` | No REAL findings remain after critic adjustments. |
| `PROCEED_WITH_GUARDS` | REAL findings exist; every one has `remediation` text. |
| `NEEDS_MORE_EVIDENCE` | Unresolved-heavy output, or classifications lack citations to gate on. |
| `DO_NOT_PROCEED` | At least one REAL finding with `severity: high` and no `remediation`. |

The gate is deterministic — same artifact in, same decision out — so CI systems can whitelist or blacklist specific levels without interpreting prose. `run.py` colour-codes the decision line and prints a one-sentence rationale; `ANTEMORTEM_JSON_SUMMARY=1` exposes the decision alongside usage counters.

Design per concern, deliberately kept vendor-neutral at the interface and vendor-native in the adapter:

| Concern | Interface (stable) | Per-provider realization |
|---|---|---|
| **Output format** | `LLMProvider.structured_complete(output_schema=AntemortemOutput)` returns a Pydantic-validated object. | Anthropic uses `messages.parse(output_format=...)`. OpenAI uses `beta.chat.completions.parse(response_format=...)`. Gemini requests `response_mime_type=application/json` with `response_schema=...` and validates the response against the same Pydantic schema. No client-side regex fallback. |
| **Caching** | CLI reports `input / cache_read / cache_write / output` on every call. | Anthropic: explicit `cache_control={"type": "ephemeral"}` on the system block. OpenAI: automatic prompt caching (system prompts over the provider's threshold cache server-side with no markers). |
| **Reasoning / thinking** | Adapter-specific. Anthropic adapter enables adaptive thinking + `effort: high` by default. OpenAI and Gemini adapters strip Anthropic-only thinking knobs. | Configurable where the provider adapter supports it; unsupported knobs are ignored rather than leaked across provider boundaries. |
| **Sampling knobs** | Omitted from the interface. | The discipline does not rely on temperature / top_p. Adapters do not send them. |
| **Refusal handling** | `ProviderError` raised with an actionable message. | Anthropic: `stop_reason == "refusal"`. OpenAI: `finish_reason == "content_filter"`. Gemini: prompt feedback / safety finish reasons / missing candidates surface as `ProviderError`. |
| **File loading** | `--repo` root, path-traversal rejected, UTF-8 with replace fallback. | Identical across providers; the discipline's own guarantee. |

The markdown document itself is **not** modified. The JSON artifact is the machine-readable output. `lint` validates the artifact against disk. This separation means parsing bugs can't corrupt your markdown.

### `antemortem lint <doc>`

Two tiers of validation, composable in CI:

1. **Pre-run (schema)**: frontmatter parses, spec section has text, at least one trap is enumerated, at least one file is listed under Recon protocol. Applies to every document.
2. **Post-run (citations)**: if `<doc>.json` exists next to the document, every input trap has a classification, every classification has a valid `path:line` or `path:line-line` citation, every cited file exists in `--repo`, and every cited line range is within that file's bounds. If `evidence_hash` is present, lint recomputes it from the cited source text. If `evidence_snippet` is present, lint requires that snippet to appear inside the cited range.

Exit `0` on pass, `1` on fail, with every violation printed on its own line. Use `gate` when CI must enforce both citation validity and the decision allowlist.

### `antemortem evidence <artifact.json>`

Inspects an existing artifact and recomputes evidence hashes from the current repository checkout. It reports missing hashes, matching hashes, mismatches, snippet mismatches, oversized ranges, and invalid citations. It never calls a provider.

```bash
antemortem evidence antemortem/my-feature.json --repo .
antemortem evidence antemortem/my-feature.json --repo . --check
antemortem evidence antemortem/my-feature.json --repo . --write-missing
```

`--write-missing` only fills absent `evidence_hash` values when citation validation succeeds. It does not overwrite mismatched hashes.

### `antemortem gate <doc>`

Runs `lint` first, then checks the sibling JSON artifact's `decision` against a caller-supplied allowlist. The default allowlist is `SAFE_TO_PROCEED,PROCEED_WITH_GUARDS`.

```bash
antemortem gate antemortem/my-feature.md --repo .
antemortem gate antemortem/my-feature.md --repo . \
  --allow SAFE_TO_PROCEED
```

Use `--no-require-artifact` only for schema-only pre-run gating; release gates should require the run artifact.

### `antemortem eval <path>`

Evaluates stored golden benchmark cases without live API calls or provider SDK calls. Each case contains a fixture repo, recon document, stored provider output, expected labels/citations/decision, and a short explanation.

```bash
antemortem eval benchmarks/golden_cases
antemortem eval benchmarks/golden_cases --json
antemortem eval benchmarks/golden_cases \
  --fail-under citation_valid_rate=1.0 \
  --fail-under decision_accuracy=0.8
```

The metrics are repo-local: they measure these committed golden cases, not general model quality and not superiority over other tools.

---

## Evidence-bound citations

Line-bound citation checks prove that a referenced location exists. Evidence-bound checks prove that the cited source text has not drifted since the artifact was produced.

`antemortem run` computes `evidence_hash` locally after citation validation. The model is not asked to invent hashes. The hash format is `sha256:<hex>` over the cited line range after LF normalization and trailing-whitespace stripping. If the model provides `evidence_snippet`, `lint` verifies that the snippet appears inside the cited range.

Default lint remains backward compatible with older artifacts that lack `evidence_hash`. CI should use strict evidence when it wants every non-UNRESOLVED finding and every new trap bound to source text:

```bash
antemortem lint antemortem/my-feature.md --repo . --strict-evidence
```

Use `antemortem evidence <artifact.json> --repo . --write-missing` when an existing artifact has valid citations but lacks hashes. Use `lint --strict-evidence` after that to enforce that no required hash is missing or stale. The evidence command is a maintenance tool; strict lint is the CI gate.

---

## Provider support

`antemortem-cli` speaks to the LLM through an `LLMProvider` Protocol. The discipline is vendor-neutral; only one seam is pluggable. Each adapter uses the structured-output path listed below, and every returned artifact object is Pydantic-validated before write. There is no client-side JSON regex-parsing anywhere in the pipeline. This matrix is validated against `src/antemortem/providers/capabilities.py`; see [Provider Compatibility](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/provider_compatibility.md).

<!-- provider-matrix:start -->
| Provider | CLI | Default model | API key env | Structured output path | Contract-tested behavior | Caveats |
|---|---|---|---|---|---|---|
| Anthropic | `--provider anthropic` | `claude-opus-4-7` | `ANTHROPIC_API_KEY` | `messages.parse(output_format=...)` | Pydantic validates parsed/dict output before artifact write. SDK exceptions and refusals surface as ProviderError. | Native Anthropic only; base_url is ignored. |
| OpenAI | `--provider openai` | `gpt-4o` | `OPENAI_API_KEY` | `beta.chat.completions.parse(response_format=...)` | Pydantic validates parsed/dict output before artifact write. SDK exceptions, content_filter, missing choices, and missing parsed output surface as ProviderError. | Requires models/endpoints that support the SDK structured parse path. |
| Gemini | `--provider gemini` | `gemini-2.5-flash` | `GEMINI_API_KEY` / `GOOGLE_API_KEY` | `Google GenAI response_schema with application/json` | Returned JSON is parsed and validated with the same Pydantic artifact schema. SDK exceptions, invalid JSON, schema errors, safety blocks, and missing candidates surface as ProviderError. | Requires Google GenAI SDK; no OpenAI-compatible base_url path. |
| OpenAI-compatible | `--provider openai --base-url <url>` | `user-supplied via --model` | `OPENAI_API_KEY` / `or any string for unauthenticated local endpoints` | `Same OpenAI parse path via configured base_url` | Pydantic validates parsed/dict output before artifact write. Same OpenAI adapter ProviderError handling. | Not universal: endpoint must implement the structured parse path; local model fidelity varies and lint remains mandatory. |
<!-- provider-matrix:end -->

**Extending:** implementing a new provider is one module. Satisfy the `LLMProvider` Protocol (one method: `structured_complete`), register it in `providers/factory.py`, add a capability entry in `providers/capabilities.py`, and add contract tests. The CLI surface and the data contract need no changes.

**The `LLMProvider` Protocol** (`src/antemortem/providers/base.py`):

```python
class LLMProvider(Protocol):
    name: str
    model: str
    def structured_complete(
        self,
        *,
        system_prompt: str,
        user_content: str,
        output_schema: type[T],
        max_tokens: int = 16000,
    ) -> tuple[T, dict[str, int]]: ...
```

One method. No SDK leakage. The system prompt is provider-neutral by construction — same prompt text works across every vendor.

---

## The data contract

Every artifact this CLI produces is Pydantic-validated. The data flows end-to-end:

```python
# Input: a markdown document the user writes
# ↓ parser.py
AntemortemDocument(
    frontmatter=Frontmatter(name=..., date=..., scope=..., status="draft"),
    spec="The change we are about to build...",
    files_to_read=["src/auth/middleware.py", "src/auth/token.py"],
    traps=[
        Trap(id="t1", hypothesis="Session token stored in cookie is not rotated on refresh", type="trap"),
        Trap(id="t2", hypothesis="Race condition on concurrent refresh", type="worry"),
    ],
)

# ↓ run.py → provider.structured_complete(output_schema=AntemortemOutput)
AntemortemOutput(
    classifications=[
        Classification(
            id="t1",
            label="REAL",
            citation="src/auth/middleware.py:45-52",
            note="The refresh path (line 48) issues a new token but leaves the old session cookie untouched.",
            severity="high",
            confidence=0.82,
            remediation="In the refresh handler, clear the prior session cookie via Set-Cookie with an expired Max-Age before issuing the new one.",
        ),
        Classification(
            id="t2",
            label="GHOST",
            citation="src/auth/token.py:72",
            note="The refresh function acquires the session lock before mutating — no race window.",
        ),
    ],
    new_traps=[
        NewTrap(
            id="t_new_1",
            hypothesis="Token rotation on refresh requires cache invalidation in the CDN layer.",
            citation="src/auth/middleware.py:88",
            note="Line 88 sets Cache-Control but does not vary by token — stale tokens survive in edge caches.",
            severity="medium",
        ),
    ],
    spec_mutations=[
        "Add: on token rotation, explicit invalidation of the old session cookie.",
        "Add: CDN cache-invalidation step in the rotation sequence.",
    ],
    # ↓ populated by critic.py, only when --critic is passed
    critic_results=[
        CriticResult(
            finding_id="t1",
            status="CONFIRMED",
            issues=[],
            counterevidence=[],
            recommended_label=None,
        ),
    ],
    # ↓ populated by decision.py, suppressed by --no-decision
    decision="PROCEED_WITH_GUARDS",
    decision_rationale="One REAL finding (t1) with concrete remediation; no high-severity finding lacks a mitigation.",
)

# ↓ lint.py verifies every citation on disk
# PASS — auth-refactor.md validates clean (schema + classifications)
```

Every field in every model is type-checked by Pydantic. A malformed response from the API raises `ValidationError` at the SDK boundary — it never pollutes the artifact. A citation that points at a line that doesn't exist in the file fails `lint` — it never pollutes the spec.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  antemortem/my-feature.md  (markdown + YAML frontmatter)     │
└────────────────┬─────────────────────────────────────────────┘
                 │  parser.py (frontmatter + regex section split)
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  AntemortemDocument (Pydantic)                               │
│    frontmatter · spec · files_to_read · traps                │
└────────────────┬─────────────────────────────────────────────┘
                 │  run.py (load files from --repo, build payload)
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  api.py → provider.structured_complete()                     │
│    ┌─ AnthropicProvider ─ messages.parse(output_format=...)  │
│    │                      thinking: adaptive, effort: high   │
│    │                      cache_control: ephemeral           │
│    ├─ OpenAIProvider    ─ beta.chat.completions.parse()      │
│    │                      response_format=AntemortemOutput   │
│    │                      (automatic prompt caching)         │
│    ├─ GeminiProvider    ─ generate_content()                 │
│    │                      response_schema=AntemortemOutput   │
│    │                      + local Pydantic validation        │
│    └─ <custom>          ─ satisfy the Protocol, done         │
└────────────────┬─────────────────────────────────────────────┘
                 │  Vendor-native schema enforcement            │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  AntemortemOutput  (first pass)                              │
│    classifications[]  (id, label, citation, note,            │
│                        severity?, confidence?, remediation?, │
│                        evidence_snippet?, evidence_hash?)    │
│    new_traps[]        (hypothesis, citation, note,            │
│                        evidence_snippet?, evidence_hash?)    │
│    spec_mutations[]   (free-form edits to your spec)         │
└────────────────┬─────────────────────────────────────────────┘
                 │  critic.py  (opt-in via --critic)            │
                 │    second provider call, asymmetric:         │
                 │    CONFIRMED / WEAKENED / CONTRADICTED /     │
                 │    DUPLICATE — only downgrades, never        │
                 │    promotes.                                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  AntemortemOutput  +  critic_results[]                       │
└────────────────┬─────────────────────────────────────────────┘
                 │  decision.py  (default on, --no-decision)    │
                 │    deterministic four-level gate over        │
                 │    severity + remediation + critic outcome.  │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  AntemortemOutput  +  decision  +  decision_rationale        │
│    decision ∈ { SAFE_TO_PROCEED, PROCEED_WITH_GUARDS,        │
│                 NEEDS_MORE_EVIDENCE, DO_NOT_PROCEED }        │
└────────────────┬─────────────────────────────────────────────┘
                 │  run.py writes JSON next to the .md
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  antemortem/my-feature.json  (audit artifact)                │
└────────────────┬─────────────────────────────────────────────┘
                 │  lint.py parses both .md and .json
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  citations.py → verify path:line + evidence binding on disk  │
│  exit 0 = trust the classifications                          │
│  exit 1 = something is fabricated or out of date             │
└──────────────────────────────────────────────────────────────┘
```

Every module has a single responsibility; the pipeline is testable end-to-end without the network. `AntemortemDocument`, `Classification`, `NewTrap`, `CriticResult`, and `AntemortemOutput` are the data contract — the same types flow from `run` through `critic` and `decision` to `lint`, so a drift in one is caught in the others.

---

## Design decisions worth defending

**Vendor-neutral interface, vendor-native adapters.** The `LLMProvider` Protocol has one method and no vendor-specific knobs. Each adapter uses the structured-output path registered in `src/antemortem/providers/capabilities.py`: Anthropic `messages.parse`, OpenAI `beta.chat.completions.parse`, and Gemini `response_schema` with local Pydantic validation. The discipline (Pydantic enforcement, disk-verified citations, stable exit codes) is identical across providers. Adding a new provider is one module plus a capability entry and contract tests; it does not touch the CLI or the data contract.

**The system prompt is written to be provider-neutral.** The ~5k-token `SYSTEM_PROMPT` in `src/antemortem/prompts.py` does not reference a specific vendor, model, or API surface. It defines the discipline in terms the LLM has to satisfy (four labels with exact definitions, citation rules with good/bad examples, scope boundary, few-shot JSON examples). Swapping providers does not require re-tuning it.

**Citations verified on disk by `lint`, not trusted.** Structured-output APIs can break schema conformance under refusal, and even well-behaved models occasionally miscount lines in long files. Trusting the model's self-reported citations is the same mistake as trusting a tested pull request is bug-free. The defense is mechanical re-verification against the source: path bounds always, evidence hashes and snippets when present. `lint` is a first-class command because CI gates need to run it without ceremony.

**JSON artifact is the output, markdown is the input.** The model could edit the markdown in place — some tools do that. We don't, for three reasons: (1) the markdown is yours, not the model's; (2) a parse bug in either direction could corrupt hours of work; (3) machine-readable JSON composes cleanly with downstream tooling (CI gates, dashboards, diff viewers). The markdown stays a human artifact.

**~5k-token system prompt, deliberately.** Both Anthropic and OpenAI cache prefixes past their respective thresholds; the prompt is sized to clear both comfortably. A shorter prompt wouldn't cache reliably; a longer one would drift from the discipline it enforces. Every substantive byte is load-bearing: role framing, input format, four labels with exact definitions, citation rules with good/bad examples, anti-patterns list, scope boundary, four few-shot JSON examples. [The full prompt](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/src/antemortem/prompts.py) is worth reading as a case study in prompt-cache-aware design.

**Pydantic v2 schemas are the data contract, not dict-shaped comments.** `Classification`, `NewTrap`, `AntemortemOutput`, `Frontmatter`, `AntemortemDocument` all flow end-to-end: the SDK validates on the API boundary, `run` writes validated JSON, `lint` validates on load. A malformed classification never gets written to disk, which means it never gets merged into main.

**Windows path normalization is cache-invariant, not cosmetic.** `src\foo.py` and `src/foo.py` render the same on disk but are different bytes in the API payload — the cache key is byte-exact. Every path is normalized to forward slashes before content is built. See `api.py:_build_user_content`. This is a 3-line fix that would silently waste ~\$15/100 runs if missed.

**Exit codes are stable and documented.** `1` means validation failed, `2` means usage or configuration is wrong, `3` means the provider call failed before a trustworthy artifact could be written, and `4` means policy blocked a gate or benchmark threshold. The full table is in [CLI Exit Codes](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/cli_exit_codes.md).

**Scope boundary is enforced in the prompt, not suggested.** The system prompt explicitly says: *"You classify what is in the provided files. You do not: speculate about files not shown, comment on architecture beyond the spec's scope, recommend the user adopt a different design, evaluate whether the change is a good idea."* If the user asks for any of those, the model is instructed to note it in `spec_mutations` as "Out of antemortem scope" and proceed. The tool does one thing.

**The critic pass is asymmetric — it only downgrades.** `--critic` adds a second provider call whose prompt (~1.5k tokens, isolated from the classifier prompt) instructs the model to adversarially re-examine every REAL and NEW finding and return one of `CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE`. The policy that consumes those statuses is deliberately one-way: a finding can move *from* REAL or NEW *to* UNRESOLVED / GHOST / dropped, and never in the other direction. A symmetric critic would contaminate its own signal; if the critic could promote UNRESOLVED to REAL, a noisy critic could fabricate findings. The asymmetry keeps the second pass conservative and fixes the cost model at one extra provider call.

**The decision gate is opt-out, not opt-in.** By default, every `run` emits one of four decisions (`SAFE_TO_PROCEED` / `PROCEED_WITH_GUARDS` / `NEEDS_MORE_EVIDENCE` / `DO_NOT_PROCEED`), selected deterministically from finding counts, `severity`, `remediation` presence, and critic outcomes. `--no-decision` exists for callers who want the raw artifact, but CI should get an opinion without asking. The gate's determinism matters: same artifact in, same decision out — no LLM call, no sampling, so downstream whitelists/blacklists on decision levels are stable across identical inputs. Teams override policy by gating on specific levels, not by tweaking thresholds inside the tool.

**Hard-wired UTF-8 with replace fallback.** Non-UTF-8 files don't crash the tool. They're read with byte-level replacement and a warning. This is the difference between "my antemortem failed because of a BOM in a YAML file" and "my antemortem ran and included a minor note about that file."

---

## What this is NOT

The discipline fails if you use it for the wrong thing. Explicit non-goals:

| This tool is NOT | Because |
|---|---|
| A code review replacement | Code review looks at the diff after it's written. Antemortem looks at the *absence* of a diff that doesn't exist yet. Different phases. Both needed. |
| A design review | Design review asks "should we build this?" Antemortem assumes the answer is yes and asks "given the existing code, what does it already tell us about the risks?" |
| A runtime bug detector | Race conditions, GC timing, network flakes, platform encoding — these live outside the files. An antemortem will not catch them. See [Limits](https://github.com/hibou04-ops/Antemortem/blob/main/docs/methodology.md#limits). |
| An LLM "second opinion" chatbot | Without the two guardrails (enumerate-first, cite-every-line), an LLM happily agrees with whatever you typed. This CLI is the enforcement mechanism. |
| A benchmark for LLM coding ability | The classifications are only as trustworthy as the citations, which `lint` re-verifies. The *discipline* is what's measured here, not the model. |
| A replacement for tests | Tests validate behavior. Antemortem validates your mental model against the source. A change should pass both. |

If you catch yourself using this tool for any of the above, you are using it wrong. The cost of wrong use is wasted calls and, worse, false confidence.

---

## Cost & performance

Per-`run` cost varies by provider and tier. Rough envelopes:

| Provider + tier | First run (write to cache) | Cached subsequent run | 100-run iteration budget |
|---|---|---|---|
| Anthropic frontier (Opus-class) | ~\$0.15–0.20 | ~\$0.10–0.12 | \$10–20 |
| Anthropic mid-tier (Sonnet-class) | ~\$0.04–0.08 | ~\$0.03–0.05 | \$3–8 |
| OpenAI frontier (`gpt-4o`) | ~\$0.08–0.15 | ~\$0.05–0.10 | \$5–15 |
| OpenAI mini-tier (`gpt-4o-mini`) | ~\$0.01–0.03 | ~\$0.005–0.015 | \$1–3 |
| Local via Ollama (`llama3.1:70b`) | free (only compute) | free | free |

Every `run` prints `input (+cache_read, +cache_write) output` and the resolved `provider / model` — cache engagement or silent failure is visible on each invocation. If `cache_read_input_tokens` is zero across consecutive runs with an unchanged prompt, a silent invalidator exists somewhere in the prompt-building pipeline and the CLI prints an explicit warning. (Local endpoints report zero cache tokens by design; ignore that warning when running against Ollama.)

The default `--max-tokens` is 16000. Typical output lands in the 1–4k range. Raising it to 128000 is supported for rare deep-surface recons.

---

## Validation

**Offline test suite, 0 network calls in normal CI.** Run it with `python -m pytest -q`. Every provider is accepted via the `LLMProvider` Protocol, which means every API test mocks the client via `SimpleNamespace` or `MagicMock`. Two benefits: deterministic CI that doesn't burn API credits, and test-time freedom to assert the *exact* shape of the request payload (model, thinking config, cache_control placement, `response_format`, sorted file order) without negotiating with a real server.

| Module | Coverage |
|---|---|
| `schema.py` | 11 tests — required fields, label enum, citation-nullable on UNRESOLVED, evidence binding fields, NewTrap id pattern, JSON roundtrip. |
| `citations.py` | 14 tests — range parsing, Windows backslash normalization, empty-string / prose / zero-line / reversed-range rejection, disk verification including path traversal. |
| `evidence_hash.py` | 14 tests — evidence hash normalization, strict-evidence lint, snippet mismatch, source drift detection, traversal-safe hash computation, run-time local hash stamping. |
| `evidence_command.py` | 5 tests — write-missing behavior, path traversal rejection, source drift detection, stable JSON output, UNRESOLVED handling. |
| `adversarial_boundaries.py` | 7 tests — path traversal in recon lists and citations, symlink escape, hidden/binary/huge/invalid-encoding file handling, malformed tables, duplicate trap IDs, empty spec/no traps/no files. |
| `claim_ledger.py` | 5 tests — current ledger validity, missing source detection, qualitative marker enforcement, location drift detection, and README ledger-link coverage. |
| `demo_replay.py` | 3 tests — README replay command, stored capture freshness against `demo_recon.py`, and demo-doc claims for labels, final decision, and lint verification. |
| `examples_gallery.py` | 5 tests — gallery case structure, offline lint for every artifact, evidence hashes, CI gate blocking behavior, and docs link coverage. |
| `github_templates.py` | 3 tests — issue template coverage, trust-context fields, and PR checklist requirements. |
| `launch_kit_docs.py` | 5 tests — launch note coverage, reproducible command presence, hype/adoption guardrails, limitations, and local link validity. |
| `package_metadata.py` | 5 tests — PyPI description length, README content type, project URLs, Python classifier/CI parity, and PyPI rendering-check docs. |
| `parser.py` | 11 tests — frontmatter validation, section extraction, `recon-protocol` vs `pre-recon` disambiguation, trap-table parsing with placeholder-row filtering. |
| `lint.py` | 11 tests — both tiers (schema-only and artifact), every violation path, exit codes. |
| `post_release_check.py` | 8 tests — mocked PyPI/GitHub success path, dry-run and skip-network modes, PyPI/tag/install failures, local docs coverage, stable JSON, and analytics wording guardrails. |
| `providers/` | Factory rejects unknown names, uses defaults, passes through `--base-url`; Anthropic adapter builds expected kwargs / raises on refusal / coerces dict-output; OpenAI adapter maps `prompt_tokens_details.cached_tokens` → `cache_read_input_tokens` / raises on content_filter / raises on missing parsed; Gemini adapter builds `generate_content` request shape, validates JSON locally, rejects malformed/schema-invalid JSON, maps usage metadata. |
| `provider_contracts.py` | 14 tests — capability registry coverage, schema-compatible output accepted, malformed output rejected, provider errors surfaced, no provider SDK imports during offline stubs. |
| `api.py` | 5 tests — user-payload shape, Windows path normalization, provider-delegation contract, error propagation. |
| `critic.py` | 12 tests — payload assembly blocks (`<files>`, `<spec>`, `<traps>`, `<first_pass>`), provider-delegation contract, each of the four status-policy outcomes (`CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE`) applied deterministically over the first-pass artifact. |
| `decision.py` | 13 tests — all four decision outcomes, plus edge cases: empty classifications, REAL-with-remediation vs REAL-without, severity-high gating, critic-downgrade interaction, unresolved-only inputs. |
| `run.py` | 8 tests — full flow with mocked provider, error paths, warnings, JSON-summary env var, cache-miss warning surface, critic pass delegation. |
| `doctor.py` | 6 tests — READY preflight, missing file failure, duplicate trap id strictness, path traversal rejection, binary file skip, stable JSON output. |
| `init.py` | 6 tests — basic + enhanced templates, `--force`, path traversal rejection, ISO date frontmatter. |
| `eval_benchmarks.py` | 9 tests — JSON/table output, threshold failure, unknown threshold rejection, golden-case directory contract, adversarial case coverage, denominator checks, malformed-case isolation, no provider construction. |
| `repo_consistency.py` | 7 tests — version mismatch, stale decision enum, stale command count, allowlisted historical references, exact public test-count rejection, and provider matrix drift. |
| `generate_readme_claims.py` | 5 tests — command-registry drift, generated-claim freshness detection, Korean/English enum parity, benchmark JSON ingestion, and platform-independent claim rendering. |
| `generate_release_notes.py` | 4 tests — explicit-file fallback, git-range input, benchmark JSON-only metrics, and `--output` CLI behavior. |
| `rc_freeze_check.py` | 4 tests — release-audit coverage, static failure inventory, stale `dist/` detection, and parent release-audit mode. |
| `release_audit.py` | 4 tests — mocked success path, first-failure exit, stable JSON summary, continue-on-error failure inventory. |
| `scope_freeze_check.py` | 6 tests — current public docs, feature-promise detection, unimplemented command detection, deferred roadmap allowance, comparative-claim guardrail, and allowlist behavior. |
| `smoke_wheel_install.py` | 10 tests — mocked wheel build/install path, build failure stop, missing fixture failure, package-data boundary documentation, missing package module, installed CLI failure, version mismatch, and tooling blockers. |
| `ci_workflow.py` | 4 tests — workflow name/badge parity, supported Python matrix, offline trust commands, separate wheel-smoke job without provider API keys. |
| `cli.py` | 3 tests — `--help` lists the registered command surface, `--version`, no-args-prints-help. (Per-command behavior covered under `run.py` / `lint.py` / `init.py` / `gate.py`.) |
| `cli_help_text.py` | 5 tests — help snapshots for every command, README Quick Start command parity, actionable `FAIL` / `Why` / `Next` messages, policy exit codes, exit-code docs matching constants. |
| `trust_model_docs.py` | 3 tests — trust-model topic coverage, README link coverage, and no unbacked comparative claim language. |
| `toolkit_positioning_docs.py` | 4 tests — toolkit role coverage, README link coverage, local/external link allowlist, and hype-claim guardrails. |

Run with `python -m pytest -q`. The generated public claim block intentionally avoids exact collected test counts because pytest collection can differ across OS and Python matrix entries.

## Repository self-checks

```bash
python scripts/generate_readme_claims.py --check
python scripts/check_repo_consistency.py
```

These checks verify generated claim blocks plus README versions, badges, command counts, command names, decision enums, package naming, provider rows, and benchmark-backed claims against `pyproject.toml`, the Typer app, `decision.py`, provider registration, and benchmark JSON.

For release readiness, run the full local audit:

```bash
python scripts/release_audit.py
```

It runs tests, generated-claim checks, the offline benchmark, build, `twine check`, and the installed-wheel smoke test; it does not publish. See [Release Hygiene](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/release_hygiene.md).

GitHub Actions workflow `CI` runs the offline trust checks on Ubuntu and Windows for the supported Python versions, uploads benchmark JSON, and runs wheel smoke installation in a separate job. Normal CI does not require provider API keys.

To verify the wheel entrypoint directly:

```bash
python scripts/smoke_wheel_install.py
```

## Benchmark-backed claims

```bash
antemortem eval benchmarks/golden_cases --json
```

The committed golden benchmark set measures `trap_label_accuracy`, `new_trap_precision`, `citation_valid_rate`, `false_real_rate`, `false_ghost_rate`, `unresolved_rate`, `decision_accuracy`, `critic_flip_rate`, `high_severity_block_rate`, and `schema_parse_success_rate` against stored outputs. The harness is offline: it reads `provider_output.json`, validates it with the same Pydantic artifact schema, verifies citations against each fixture `repo/`, and compares results to `expected.json`.

The committed cases include adversarial trust fixtures for evidence snippet drift, over-broad citation ranges, path traversal citations, binary-file skips, link escape attempts, duplicate trap ids, missing files that should stay `UNRESOLVED`, hashed `NEW` traps, exact-line `GHOST` evidence, and high-severity `REAL` blockers.

Use thresholds in CI when a metric is meant to be invariant for the current fixture set:

```bash
antemortem eval benchmarks/golden_cases \
  --fail-under decision_accuracy=0.8
```

These are repo-local measurements over the committed golden cases. They are not claims of superiority over other tools or of general model quality.

---

## Toolkit positioning

This repository is the CLI/CI verification surface for pre-implementation reconnaissance. It owns:

- risk classification before code changes
- citation/evidence verified artifacts
- local `doctor` / `lint` / `evidence` / `eval` / `gate` checks

Related tools are adjacent, not prerequisites:

- `omegaprompt`: calibration / optimization layer
- `omega-lock`: audit / post-optimization lock layer
- `mini-omega-lock`: empirical live API preflight
- `mini-antemortem-cli`: deterministic analytical preflight, if applicable

The role map and claim boundaries are documented in [Toolkit Positioning](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/docs/toolkit_positioning.md). This README stays focused on the packaged CLI.

---

## FAQ for skeptics

**Isn't this just pre-mortem (Klein, 2007) with a new name?**

No. Gary Klein's pre-mortem is a *team-level strategic exercise* ("assume we've failed; what caused it?") run over 30–60 minutes at project commitment time. Antemortem is *change-level, solo, source-code-grounded, tactical*, discharged in 15–30 minutes. Pre-mortem asks *"should we do this?"* Antemortem asks *"given that we will, what does the existing code already tell us about the risks of this specific approach?"* They compose — pre-mortem first, antemortem per-change.

**Why not just ask the LLM "review my spec before I code"?**

That is the degenerate case this tool exists to prevent. Without the two guardrails, an LLM happily agrees with whatever you wrote. You get a list of generic risks mixed with genuine ones, no way to tell them apart, and no pressure on the model to back up claims. The `file:line` requirement plus `lint`'s re-verification is the difference between "opinion" and "evidence."

**Does the choice of model matter?**

The discipline is vendor-neutral by design, but model capability matters. The tool asks the model to trace multi-file call chains, classify with exact `file:line` citations, and respect a strict JSON schema. Frontier-tier models (Anthropic Opus-class, OpenAI `gpt-4o` or better, or a capable local reasoner) clear this bar; smaller models may produce more UNRESOLVED labels, which is still a valid outcome — just a less useful one. `lint` mechanically catches fabricated citations regardless of model, so the worst case with a weaker model is "low signal," not "wrong signal."

**Won't the model just make up line numbers?**

It sometimes will. That is why `lint` exists. Every citation is parsed, the file is loaded, and the line range is checked against actual file bounds. When `evidence_hash` or `evidence_snippet` is present, the cited source text is checked too. A hallucinated citation fails the lint. The model is instructed that *"A fabricated line number is strictly worse than UNRESOLVED — UNRESOLVED is honest, fabrication is not,"* and the discipline backs this up with mechanical verification.

**Does this work on closed-source or private code?**

Yes. The LLM reads what you give it; it does not need a public repo. The only constraint is that citations in a published case study should quote enough inline context to be verifiable by readers without repo access.

**What about an IDE plugin? A web UI?**

Out of scope, by design. The CLI is the right surface for a CI-gate tool — you can `antemortem lint` in GitHub Actions, pre-commit hooks, or a local Makefile. A web UI would add state and auth; a plugin would couple to one IDE's extension API. Both are worse for the primary use case (merge-gate).

**I'm in Go / Rust / TypeScript. Can I use this?**

Yes. Antemortem is language-agnostic — it reads *files*, not Python ASTs. The CLI is a Python package, but the target repo can be anything. The case study in omega-lock is Python; the discipline works the same way on a Rust crate or a TypeScript monorepo.

**How is this different from Cursor / Claude Code / Aider's "plan" mode?**

Those tools integrate planning into the editing loop — useful, but the plan lives in the same session as the implementation. Antemortem is a *separate artifact* you keep. Six months from now, when the feature surprises you, you can reread `antemortem/auth-refactor.md` and see which of your assumptions broke. It is a disciplined paper trail, not an ephemeral chat.

**Why Python?**

Because the first user was building on omega-lock (Python), and because both the Anthropic and OpenAI Python SDKs have first-class structured-output paths (`messages.parse` / `beta.chat.completions.parse`). The tool is 100% offline-validatable (`lint` doesn't need the network) so Python runtime is not a hot-path constraint.

**Can I use a local model?**

An OpenAI-compatible endpoint can be used via `--base-url` only if it implements the structured-output `parse` path the SDK uses. Ollama's compatibility layer at `http://localhost:11434/v1` is reachable, but model-by-model the structured-output fidelity varies — small local models often emit JSON-shaped output that doesn't survive Pydantic's strict parse. Run `antemortem lint` before trusting a local-model artifact; lint catches fabricated citations regardless of which model produced them.

```bash
antemortem run antemortem/my-feature.md --repo . \
  --provider openai \
  --base-url http://localhost:11434/v1 \
  --model llama3.1:70b
```

### Provider compatibility caveats

`antemortem run` issues structured-output calls via the OpenAI SDK's `beta.chat.completions.parse(response_format=...)` path. Endpoints that advertise OpenAI compatibility but do not implement that path (or implement it loosely) will fail in different ways:

- **Hard fail** — endpoint returns 400 / "method not supported" → CLI surfaces a `ProviderError`. Cleanest case; switch endpoint or model.
- **Schema drift** — endpoint accepts the call but returns JSON that doesn't match `AntemortemOutput` → Pydantic `ValidationError` → CLI surfaces a readable error (no stack trace).
- **Partial fidelity** — endpoint returns valid-looking JSON but fabricates citations (line numbers don't exist, paths off-by-one). `antemortem lint` catches these post-hoc; pass `--strict-citations` to fail the run upfront when a citation doesn't resolve.

The list of endpoints the maintainers have personally validated against `parse`: OpenAI (gpt-4o family), Azure OpenAI (same models). Other endpoints — including Groq, Together.ai, OpenRouter, and Ollama — are reachable through the same code path, but model-specific behaviour is the user's responsibility to verify. A `lint` run after every classification is the recommended discipline.

### Troubleshooting

**`antemortem run` returns "Incorrect API key" / 401.** Provider SDK got a key but the key was invalid. Each provider reads its own env var — the CLI does *not* fall back across vendors:

| Provider | Accepted env vars |
|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `gemini` | `GEMINI_API_KEY` **or** `GOOGLE_API_KEY` (first non-empty wins) |

Rotate the offending key in the issuing dashboard (Anthropic / OpenAI / [Google AI Studio](https://aistudio.google.com/apikey) for Gemini) and re-export.

**"ProviderError: Gemini API key is required."** Neither `GEMINI_API_KEY` nor `GOOGLE_API_KEY` is set. Free-tier key is at <https://aistudio.google.com/apikey>.

**Sanity-check before spending budget.** Use the deterministic replay first (no keys, no network):

```bash
PYTHONIOENCODING=utf-8 python examples/demo_replay.py
antemortem lint examples/demo_antemortem.md --repo .
```

If that passes, only then move to a live `antemortem run`.

**Citations look right but `lint` fails.** The model fabricated `file:line` references that don't resolve on disk — exactly the failure mode `lint` is designed to catch. Pass `--strict-citations` to fail upfront on any unresolvable citation rather than catching it at gate time.

---

## Prior art & credit

The two ideas this tool stands on:

- **Pre-mortem** — Gary Klein, *"Performing a Project Premortem,"* Harvard Business Review, September 2007. The team-strategic version of the idea.
- **The Winchester defense** — originally a quant-finance discipline: *kill criteria must be declared before the run, and cannot be relaxed after.* Used here to argue that `lint` must mechanically verify citations at gate time, not rely on the model's self-report. See omega-lock's [`docs/methodology.md § Kill criteria`](https://github.com/hibou04-ops/omega-lock/blob/main/src/omega_lock/kill_criteria.py) for the parameter-calibration analog.

The naming is explicit: *postmortem* (after death) → *antemortem* (before death). The methodology emerged during the `omega_lock.audit` submodule build in April 2026 and was documented in [hibou04-ops/Antemortem](https://github.com/hibou04-ops/Antemortem).

---

## Status & roadmap

v0.10.2 is **alpha**. The CLI contract (seven commands, flags, exit codes) is stable. The JSON artifact schema remains additive in the alpha line; breaking output-shape changes are deferred until an explicit contract-lock release. Prompt iteration continues only when the change can be checked by offline tests, recorded artifacts, or documented replay commands.

Semver applies strictly from v1.0.

**Shipped**
- **v0.2** — scaffold (`init`), classify (`run` against Claude Opus 4.x), lint (schema + disk-verified citations). The foundational three-command CLI surface.
- **v0.3** — `LLMProvider` Protocol and `providers/` package; Anthropic and OpenAI adapters using each vendor's strongest native schema-enforcement path; any OpenAI-compatible endpoint via `--base-url` (Azure, Groq, Together.ai, OpenRouter, local Ollama).
- **v0.4** — `--critic` asymmetric second-pass review (downgrades only); four-level decision gate (`SAFE_TO_PROCEED` / `PROCEED_WITH_GUARDS` / `NEEDS_MORE_EVIDENCE` / `DO_NOT_PROCEED`); optional per-finding `severity` / `remediation` / `confidence`.

**Current release-hygiene track**
- Keep public README claims tied to source of truth through `python scripts/check_repo_consistency.py`.
- Dogfood on diverse real repos only when outcomes are recorded as artifacts or reproducible commands.
- Record a reference classification-quality benchmark before making quantitative prompt-quality claims.

**Next measurement track**
- Add benchmark fixtures for prompt revisions and critic-pass cost/benefit.
- Add a run-diff command only after the artifact comparison contract is covered by tests.
- Second `cache_control` breakpoint on the files block for iterative same-repo runs.
- Official GitHub Action for CI lint gating.

**v1.0 (contract lock)**
- Public schema versioning (`antemortem.schema.json` published separately).
- Semver guarantees on output JSON shape, decision enum, and exit-code contract.
- HTML renderer for the JSON artifact (printable debrief view).

**Explicitly out of scope**: web dashboard, database-backed history, multi-user tenancy, proprietary hosting.

Full changelog: [CHANGELOG.md](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/CHANGELOG.md).

---

## Design principles, in one page

The whole tool in one page, if you only read one section:

1. **You enumerate first, the model reads second.** Anchoring is the failure mode most "plan-review" workflows bake in on the first turn. `antemortem init` gives you the scaffold; you fill in spec + traps + files *before* the LLM sees anything. That ordering is the defense, not a style preference.
2. **A citation the `lint` can't verify is not evidence.** Structured-output APIs parse malformed JSON as "parse error"; they do not catch a line number that's off by seven. The mechanical check — load the file, check bounds — is the only defense. It is a first-class command, not a `--strict` flag.
3. **UNRESOLVED is a valid outcome.** A fabricated line number is strictly worse than an honest *"no evidence in the provided files."* The system prompt is explicit about this, and the discipline rewards it.
4. **The second pass can only downgrade.** `--critic` is asymmetric by construction: CONFIRMED / WEAKENED / CONTRADICTED / DUPLICATE can move a finding *toward* UNRESOLVED / GHOST / dropped, never the other way. The tradeoff is explicit: one extra provider call for a conservative review filter.
5. **The decision is an enum, not a prose recommendation.** `SAFE_TO_PROCEED` / `PROCEED_WITH_GUARDS` / `NEEDS_MORE_EVIDENCE` / `DO_NOT_PROCEED` are what CI whitelists on. Teams pick their own policy over the four levels; the tool does not invent a threshold.
6. **Vendor-neutral interface, vendor-native adapters.** One Protocol method (`structured_complete`). Each provider uses its registered structured-output path — Anthropic `messages.parse`, OpenAI `beta.chat.completions.parse`, Gemini `response_schema` plus local Pydantic validation. No client-side regex. Swap providers with a flag.
7. **The markdown is yours, the JSON is the machine's.** The model never edits your markdown. Classifications go to a sibling `.json` file. Parse bugs in either direction cannot corrupt your source artifact.
8. **Dogfood with artifacts.** Non-trivial self-changes should attach an antemortem document or another reproducible verification artifact. The case studies in [the methodology repo](https://github.com/hibou04-ops/Antemortem/tree/main/examples) are from this codebase and include notes on what each recon missed.

---

## Contributing

Case studies go in a PR under `examples/` in the [Antemortem methodology repo](https://github.com/hibou04-ops/Antemortem) — they are the most valuable contribution and the hardest to produce. The bar is *"every classification cites `file:line`; post-implementation note exists; honest about what the recon missed."*

Tool-level contributions (new CLI flags, schema fields, prompt edits) belong in this repo as PRs against `main`. Attach the antemortem document for the change itself where feasible — we dogfood the tool on its own development.

---

## Citing

```
antemortem-cli v0.10.2 — tooling for the Antemortem pre-implementation reconnaissance discipline.
https://github.com/hibou04-ops/antemortem-cli, 2026.
```

For the underlying methodology:
```
Antemortem methodology — AI-assisted pre-implementation reconnaissance for software changes.
https://github.com/hibou04-ops/Antemortem, 2026.
```

---

## License

Apache 2.0. See [LICENSE](https://github.com/hibou04-ops/antemortem-cli/blob/v0.10.2/LICENSE).

**License history.** PyPI distributions of versions 0.2.0, 0.3.0, and 0.4.0 were shipped with an MIT `LICENSE` file. The repository was relicensed to Apache 2.0 on 2026-04-22 (commit `f49af09`); 0.5.0 (2026-04-28) and all later versions ship under Apache 2.0. Anyone who installed 0.4.0 or earlier holds an MIT license to that copy — license changes do not apply retroactively.

## Colophon

Designed, implemented, and shipped solo. The offline suite runs with `python -m pytest -q`; CI uses mocked providers and zero live API calls.
