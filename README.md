# antemortem-cli

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![PyPI](https://img.shields.io/badge/pypi-0.4.0-blue.svg)](https://pypi.org/project/antemortem/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](#status)
[![Tests](https://img.shields.io/badge/tests-111%20passing-brightgreen.svg)](tests/)
[![Providers](https://img.shields.io/badge/providers-anthropic%20%7C%20openai%20%7C%20openai--compatible-informational.svg)](#provider-support)
[![Methodology](https://img.shields.io/badge/methodology-Antemortem-blueviolet.svg)](https://github.com/hibou04-ops/Antemortem)

> **Your next feature has seven risks. Five are imaginary. Two you haven't named yet.**
>
> An antemortem finds out which is which — from the code, in fifteen minutes, with file-and-line citations the lint can verify. Before you write the diff. Works with any frontier LLM: Anthropic, OpenAI, or any OpenAI-compatible endpoint (Azure OpenAI, Groq, Together.ai, OpenRouter, local Ollama).

```bash
pip install antemortem
```

한국어 README: [README_KR.md](README_KR.md)

---

## 30-second tour

```bash
# 1. Scaffold a document from the template.
antemortem init auth-refactor
# writes antemortem/auth-refactor.md — a markdown + YAML-frontmatter doc
#   § 1 Spec                     ← you write the change you're about to build
#   § 2 Traps hypothesized       ← you enumerate what might go wrong
#   § 3 Recon protocol           ← you list the files the model should read
#   § 4–7 (filled by `run`)       ← classifications, new traps, decision

# 2. Edit the markdown.  You write the spec + traps + file list yourself.
#    The model never frames your risk list — that's the anchoring defense.

# 3. Run the recon.  One API call; Pydantic-enforced structured output.
antemortem run antemortem/auth-refactor.md --repo .
# writes antemortem/auth-refactor.json with REAL / GHOST / NEW / UNRESOLVED
# labels + file:line citations for every classification.
# Optional: --critic adds a second pass that can only downgrade
#          (CONFIRMED / WEAKENED / CONTRADICTED / DUPLICATE).

# 4. Lint the result.  Exit 0 = citations verify on disk, the decision is
#    trustworthy. Exit 1 = a cited line range doesn't exist, stop.
antemortem lint antemortem/auth-refactor.md
```

`run` prints a colour-coded decision on each invocation — one of `SAFE_TO_PROCEED` / `PROCEED_WITH_GUARDS` / `NEEDS_MORE_EVIDENCE` / `DO_NOT_PROCEED`. CI pipelines gate on the decision enum; humans gate on the one-line rationale. No prose parsing.

---

## Table of Contents

- [The failure mode this solves](#the-failure-mode-this-solves)
- [How it compares](#how-it-compares)
- [Worked example: a real ghost trap](#worked-example-a-real-ghost-trap)
- [The three commands](#the-three-commands)
- [Provider support](#provider-support)
- [The data contract](#the-data-contract)
- [Architecture](#architecture)
- [Design decisions worth defending](#design-decisions-worth-defending)
- [What this is NOT](#what-this-is-not)
- [Cost & performance](#cost--performance)
- [Validation](#validation)
- [The 3-layer stack](#the-3-layer-stack)
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
2. **Every non-UNRESOLVED classification carries a `file:line` citation.** The schema is Pydantic-enforced at the SDK boundary, and `antemortem lint` re-verifies every citation against disk. Hallucinated line numbers fail the build.

Without these two guardrails, you have traded one form of hand-waving for another. **With** them, you have a cheap, mechanical screening step that runs in fifteen minutes and catches a category of error that testing and code review do not.

---

## How it compares

Pre-implementation risk surfacing is not new. What `antemortem-cli` adds is the *discipline around the LLM call* — two guardrails (anchoring defense, citation verification) plus a deterministic decision gate, none of which are opinions you can wave away.

| Approach | What it catches | What it misses | What antemortem-cli adds |
|---|---|---|---|
| **Pre-mortem** (Klein, 2007) | Strategic framing risks — whether the project should exist. | Source-level specifics (no code is read). Solo use cases. | Change-level, source-code-grounded, solo, 15-min discharge. Pre-mortem *and* antemortem compose — they operate at different scopes. |
| **"Explain my plan" to an LLM** | Obvious fluency mistakes. | The LLM anchors on your framing and agrees. No citation. No disk check. Answers *"probably fine"* to everything. | Enumerate-before-show, `file:line` citations mandatory, `lint` re-verifies on disk. The degenerate case this tool exists to prevent. |
| **Code review on the PR** | Mistakes that survived into the diff. | Mistakes baked in *before* the first keystroke — the ones most expensive to fix. | Runs before the diff exists. Catches the category review cannot see. |
| **Tests** | Behavior deviations from expectation. | Mistaken expectations. | Validates the *plan* against the existing code, not the code against the plan. |
| **IDE-integrated planning** (Cursor, Claude Code, Aider) | Same-session, conversational guidance. | Plan lives in the chat; no artifact you can reread six months later. No mechanical citation check. | A persistent markdown + JSON artifact per change. Disk-verified citations. Four-level decision enum CI can gate on. |

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

## The three commands

### `antemortem init <name>`

Scaffolds a document from the official template. YAML frontmatter (`name`, `date`, `scope`, `reversibility`, `status`, `template`) plus a seven-section body. `--enhanced` swaps to the richer template: calibration dimensions (evidence strength, blast radius, reversibility), fine-grained classification subtypes (`REAL-structural`, `GHOST-mitigated`, `NEW-spec-gap`, …), an explicit skeptic pass on every REAL/NEW finding, and a decision-first output structure.

```bash
antemortem init my-feature                  # basic
antemortem init prod-migration --enhanced   # for high-stakes changes
```

Templates are vendored from [Antemortem](https://github.com/hibou04-ops/Antemortem) under Apache 2.0.

### `antemortem run <doc>`

Parses the document, extracts the spec + traps table + listed files, loads file contents from `--repo`, calls the configured provider with a frozen system prompt, and writes the classifications to a JSON audit artifact alongside the markdown (`<doc>.json`).

```bash
# Anthropic (default)
antemortem run antemortem/my-feature.md --repo .

# OpenAI
antemortem run antemortem/my-feature.md --repo . --provider openai

# OpenAI-compatible endpoint (local Ollama, Azure, Groq, etc.)
antemortem run antemortem/my-feature.md --repo . \
  --provider openai \
  --model llama3.1:70b \
  --base-url http://localhost:11434/v1

# With the optional second-pass critic (~2x API cost, high-stakes only)
antemortem run antemortem/my-feature.md --repo . --critic
```

**Optional second pass — `--critic`.** The critic re-reads every REAL and NEW finding against the same evidence and returns exactly one of `CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE`. The dedicated ~1.5k-token critic prompt is explicitly asymmetric: the critic can only downgrade. `WEAKENED` → `UNRESOLVED`; `CONTRADICTED` → `GHOST` or `UNRESOLVED` based on counterevidence; `DUPLICATE` → dropped; `CONFIRMED` → unchanged. The asymmetry is load-bearing. A critic that can promote would contaminate its own quality signal; one that only downgrades is a strict quality multiplier at the cost of one extra call. Off by default. Enable on changes where a false REAL is expensive.

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
| **Output format** | `LLMProvider.structured_complete(output_schema=AntemortemOutput)` returns a Pydantic-validated object. | Anthropic uses `messages.parse(output_format=...)`. OpenAI uses `beta.chat.completions.parse(response_format=...)`. Both enforce schema server-side; no client-side regex fallback. |
| **Caching** | CLI reports `input / cache_read / cache_write / output` on every call. | Anthropic: explicit `cache_control={"type": "ephemeral"}` on the system block. OpenAI: automatic prompt caching (system prompts over the provider's threshold cache server-side with no markers). |
| **Reasoning / thinking** | Adapter-specific. Anthropic adapter enables adaptive thinking + `effort: high` by default. OpenAI adapter passes the model's native behavior through. | Configurable per provider. A first-class reasoning-effort passthrough for OpenAI `o1` / `o3`-class models is on the v0.5 track. |
| **Sampling knobs** | Omitted from the interface. | The discipline does not rely on temperature / top_p. Adapters do not send them. |
| **Refusal handling** | `ProviderError` raised with an actionable message. | Anthropic: `stop_reason == "refusal"`. OpenAI: `finish_reason == "content_filter"`. |
| **File loading** | `--repo` root, path-traversal rejected, UTF-8 with replace fallback. | Identical across providers; the discipline's own guarantee. |

The markdown document itself is **not** modified. The JSON artifact is the machine-readable output. `lint` validates the artifact against disk. This separation means parsing bugs can't corrupt your markdown.

### `antemortem lint <doc>`

Two tiers of validation, composable in CI:

1. **Pre-run (schema)**: frontmatter parses, spec section has text, at least one trap is enumerated, at least one file is listed under Recon protocol. Applies to every document.
2. **Post-run (citations)**: if `<doc>.json` exists next to the document, every input trap has a classification, every classification has a valid `path:line` or `path:line-line` citation, every cited file exists in `--repo`, and every cited line range is within that file's bounds.

Exit `0` on pass, `1` on fail, with every violation printed on its own line. Plug into CI as the merge gate: *"no PR merges unless its antemortem lints clean."*

---

## Provider support

`antemortem-cli` speaks to the LLM through an `LLMProvider` Protocol. The discipline is vendor-neutral; only one seam is pluggable. Each adapter uses its vendor's strongest native schema-enforcement mechanism — no client-side JSON regex-parsing anywhere in the pipeline.

| Provider | Flag | Default model | Env var | Native structured output | Notes |
|---|---|---|---|---|---|
| Anthropic | `--provider anthropic` (default) | `claude-opus-4-7` | `ANTHROPIC_API_KEY` | `messages.parse` with explicit `cache_control` | Adaptive thinking + `effort: high` enabled by default. |
| OpenAI | `--provider openai` | `gpt-4o` | `OPENAI_API_KEY` | `beta.chat.completions.parse` with `response_format` | Automatic prompt caching when system prompt ≥ provider threshold. |
| OpenAI-compatible | `--provider openai --base-url <url>` | user-supplied via `--model` | `OPENAI_API_KEY` (or any string on unauthenticated local endpoints) | Same path as OpenAI | Covers Azure OpenAI, Groq, Together.ai, OpenRouter, local Ollama (`http://localhost:11434/v1`). |

**Extending:** implementing a new provider is one module. Satisfy the `LLMProvider` Protocol (one method: `structured_complete`), register it in `providers/factory.py`, add a row in this table. The CLI surface and the data contract need no changes.

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
    # ↓ populated by critic.py, only when --critic is passed (v0.4)
    critic_results=[
        CriticResult(
            finding_id="t1",
            status="CONFIRMED",
            issues=[],
            counterevidence=[],
            recommended_label=None,
        ),
    ],
    # ↓ populated by decision.py, suppressed by --no-decision (v0.4)
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
│    └─ <custom>          ─ satisfy the Protocol, done         │
└────────────────┬─────────────────────────────────────────────┘
                 │  Vendor-native schema enforcement            │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  AntemortemOutput  (first pass)                              │
│    classifications[]  (id, label, citation, note,            │
│                        severity?, confidence?, remediation?) │
│    new_traps[]        (hypothesis, citation, note, ...)      │
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
│  citations.py → verify every path:line on disk               │
│  exit 0 = trust the classifications                          │
│  exit 1 = something is fabricated or out of date             │
└──────────────────────────────────────────────────────────────┘
```

Every module has a single responsibility; the pipeline is testable end-to-end without the network. `AntemortemDocument`, `Classification`, `NewTrap`, `CriticResult`, and `AntemortemOutput` are the data contract — the same types flow from `run` through `critic` and `decision` to `lint`, so a drift in one is caught in the others.

---

## Design decisions worth defending

**Vendor-neutral interface, vendor-native adapters.** The `LLMProvider` Protocol has one method and no vendor-specific knobs. Each adapter uses its vendor's strongest native schema-enforcement path — `messages.parse` on Anthropic, `beta.chat.completions.parse` on OpenAI — and its native caching semantics. The discipline (Pydantic enforcement, disk-verified citations, stable exit codes) is identical across providers. Adding a new provider is one module; it doesn't touch the CLI or the data contract.

**The system prompt is written to be provider-neutral.** The ~5k-token `SYSTEM_PROMPT` in `src/antemortem/prompts.py` does not reference a specific vendor, model, or API surface. It defines the discipline in terms the LLM has to satisfy (four labels with exact definitions, citation rules with good/bad examples, scope boundary, few-shot JSON examples). Swapping providers does not require re-tuning it.

**Citations verified on disk by `lint`, not trusted.** Structured-output APIs can break schema conformance under refusal, and even well-behaved models occasionally miscount lines in long files. Trusting the model's self-reported citations is the same mistake as trusting a tested pull request is bug-free. The *only* defense is re-verification against the source. `lint` is a first-class command, not a `--strict` flag, because CI gates need to run it without ceremony.

**JSON artifact is the output, markdown is the input.** The model could edit the markdown in place — some tools do that. We don't, for three reasons: (1) the markdown is yours, not the model's; (2) a parse bug in either direction could corrupt hours of work; (3) machine-readable JSON composes cleanly with downstream tooling (CI gates, dashboards, diff viewers). The markdown stays a human artifact.

**~5k-token system prompt, deliberately.** Both Anthropic and OpenAI cache prefixes past their respective thresholds; the prompt is sized to clear both comfortably. A shorter prompt wouldn't cache reliably; a longer one would drift from the discipline it enforces. Every substantive byte is load-bearing: role framing, input format, four labels with exact definitions, citation rules with good/bad examples, anti-patterns list, scope boundary, four few-shot JSON examples. [The full prompt](src/antemortem/prompts.py) is worth reading as a case study in prompt-cache-aware design.

**Pydantic v2 schemas are the data contract, not dict-shaped comments.** `Classification`, `NewTrap`, `AntemortemOutput`, `Frontmatter`, `AntemortemDocument` all flow end-to-end: the SDK validates on the API boundary, `run` writes validated JSON, `lint` validates on load. A malformed classification never gets written to disk, which means it never gets merged into main.

**Windows path normalization is cache-invariant, not cosmetic.** `src\foo.py` and `src/foo.py` render the same on disk but are different bytes in the API payload — the cache key is byte-exact. Every path is normalized to forward slashes before content is built. See `api.py:_build_user_content`. This is a 3-line fix that would silently waste ~\$15/100 runs if missed.

**`run` exits 2 on environment issues, 1 on content issues.** Exit codes are a contract with CI systems: `1` = content problem the user can fix in their antemortem (missing traps, unreadable files, provider refusal); `2` = environment problem the operator fixes (missing `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, unknown `--provider`, SDK not installed). The split is explicit because mixing them makes CI triage harder.

**Scope boundary is enforced in the prompt, not suggested.** The system prompt explicitly says: *"You classify what is in the provided files. You do not: speculate about files not shown, comment on architecture beyond the spec's scope, recommend the user adopt a different design, evaluate whether the change is a good idea."* If the user asks for any of those, the model is instructed to note it in `spec_mutations` as "Out of antemortem scope" and proceed. The tool does one thing.

**The critic pass is asymmetric — it only downgrades.** `--critic` adds a second provider call whose prompt (~1.5k tokens, isolated from the classifier prompt) instructs the model to adversarially re-examine every REAL and NEW finding and return one of `CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE`. The policy that consumes those statuses is deliberately one-way: a finding can move *from* REAL or NEW *to* UNRESOLVED / GHOST / dropped, and never in the other direction. A symmetric critic would contaminate its own signal — if the critic could promote UNRESOLVED to REAL, a noisy critic would fabricate findings and the second pass would stop being a quality multiplier. The asymmetry is the defence. It also pins the cost model: worst case, `--critic` doubles API spend; best case, it silently improves precision.

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

**111 tests, 0 network calls in CI.** Every provider (current and future) is accepted via the `LLMProvider` Protocol, which means every API test mocks the client via `SimpleNamespace` or `MagicMock`. Two benefits: deterministic CI that doesn't burn API credits, and test-time freedom to assert the *exact* shape of the request payload (model, thinking config, cache_control placement, `response_format`, sorted file order) without negotiating with a real server.

| Module | Coverage |
|---|---|
| `schema.py` | 9 tests — required fields, label enum, citation-nullable on UNRESOLVED, NewTrap id pattern, JSON roundtrip. |
| `citations.py` | 14 tests — range parsing, Windows backslash normalization, empty-string / prose / zero-line / reversed-range rejection, disk verification including path traversal. |
| `parser.py` | 11 tests — frontmatter validation, section extraction, `recon-protocol` vs `pre-recon` disambiguation, trap-table parsing with placeholder-row filtering. |
| `lint.py` | 11 tests — both tiers (schema-only and artifact), every violation path, exit codes. |
| `providers/` | 19 tests — factory rejects unknown names, uses defaults, passes through `--base-url`; Anthropic adapter builds expected kwargs / raises on refusal / coerces dict-output; OpenAI adapter maps `prompt_tokens_details.cached_tokens` → `cache_read_input_tokens` / raises on content_filter / raises on missing parsed. |
| `api.py` | 5 tests — user-payload shape, Windows path normalization, provider-delegation contract, error propagation. |
| `critic.py` | 12 tests — payload assembly blocks (`<files>`, `<spec>`, `<traps>`, `<first_pass>`), provider-delegation contract, each of the four status-policy outcomes (`CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE`) applied deterministically over the first-pass artifact. |
| `decision.py` | 13 tests — all four decision outcomes, plus edge cases: empty classifications, REAL-with-remediation vs REAL-without, severity-high gating, critic-downgrade interaction, unresolved-only inputs. |
| `run.py` | 8 tests — full flow with mocked provider, error paths, warnings, JSON-summary env var, cache-miss warning surface, critic pass delegation. |
| `init.py` | 6 tests — basic + enhanced templates, `--force`, path traversal rejection, ISO date frontmatter. |
| `cli.py` | 3 tests — `--help` lists three commands, `--version`, no-args-prints-help. (Per-command behavior covered under `run.py` / `lint.py` / `init.py`.) |

Run with `uv run pytest -q`. Typical wall time: under 0.5s.

---

## The 3-layer stack

This CLI is the third tier of a layered discipline, not a point tool:

```
         ┌─────────────────────────────────────────────┐
 Layer 3 │  antemortem-cli  (this repo)                │  "Practice the discipline"
         │  0.4.0 — CLI + lint + multi-provider        │
         │          + critic + decision gate           │
         └────────────────────┬────────────────────────┘
                              │ operationalizes
                              ▼
         ┌─────────────────────────────────────────────┐
 Layer 2 │  Antemortem  (methodology)                  │  "Define the discipline"
         │  v0.1.1 — protocol, templates, case studies │
         └────────────────────┬────────────────────────┘
                              │ demonstrated by
                              ▼
         ┌─────────────────────────────────────────────┐
 Layer 1 │  omega-lock  (reference implementation)     │  "Shipped evidence"
         │  0.1.4 — Python calibration audit framework │
         └─────────────────────────────────────────────┘
```

- **[omega-lock](https://github.com/hibou04-ops/omega-lock)** — Python calibration framework, the first project the Antemortem discipline was *practiced on*. Its `omega_lock.audit` submodule was built using the 15-minute antemortem recon whose ghost trap is cited above.
- **[Antemortem](https://github.com/hibou04-ops/Antemortem)** — the methodology that crystallized from that build: the seven-step protocol, the basic and enhanced templates, the first case study. Docs-only.
- **antemortem-cli** (this repo) — the tooling that removes the friction: scaffold with `init`, classify with `run`, verify with `lint`. Three commands, one data contract, disk-verified citations.

A fourth repo, **[omegaprompt](https://github.com/hibou04-ops/omegaprompt)**, applies omega-lock's calibration engine to prompt engineering — showing the discipline pattern transfers across domains.

The layering matters for correctness: the methodology was validated by a real shipped artifact (omega-lock 0.1.4 on PyPI, 176 tests) *before* this CLI was built. The tool automates a protocol that is already known to work — not a protocol invented alongside the tool.

---

## FAQ for skeptics

**Isn't this just pre-mortem (Klein, 2007) with a new name?**

No. Gary Klein's pre-mortem is a *team-level strategic exercise* ("assume we've failed; what caused it?") run over 30–60 minutes at project commitment time. Antemortem is *change-level, solo, source-code-grounded, tactical*, discharged in 15–30 minutes. Pre-mortem asks *"should we do this?"* Antemortem asks *"given that we will, what does the existing code already tell us about the risks of this specific approach?"* They compose — pre-mortem first, antemortem per-change.

**Why not just ask the LLM "review my spec before I code"?**

That is the degenerate case this tool exists to prevent. Without the two guardrails, an LLM happily agrees with whatever you wrote. You get a list of generic risks mixed with genuine ones, no way to tell them apart, and no pressure on the model to back up claims. The `file:line` requirement plus `lint`'s re-verification is the difference between "opinion" and "evidence."

**Does the choice of model matter?**

The discipline is vendor-neutral by design, but model capability matters. The tool asks the model to trace multi-file call chains, classify with exact `file:line` citations, and respect a strict JSON schema. Frontier-tier models (Anthropic Opus-class, OpenAI `gpt-4o` or better, or a capable local reasoner) clear this bar; smaller models may produce more UNRESOLVED labels, which is still a valid outcome — just a less useful one. `lint` mechanically catches fabricated citations regardless of model, so the worst case with a weaker model is "low signal," not "wrong signal."

**Won't the model just make up line numbers?**

It sometimes will. That is why `lint` exists. Every citation is parsed, the file is loaded, and the line range is checked against actual file bounds. A hallucinated citation fails the lint. The model is instructed that *"A fabricated line number is strictly worse than UNRESOLVED — UNRESOLVED is honest, fabrication is not,"* and the discipline backs this up with mechanical verification.

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

Yes — any OpenAI-compatible endpoint works via `--base-url`. Ollama's compatibility layer at `http://localhost:11434/v1` is the zero-config default:

```bash
antemortem run antemortem/my-feature.md --repo . \
  --provider openai \
  --base-url http://localhost:11434/v1 \
  --model llama3.1:70b
```

The lint discipline (disk-verified citations) is unchanged. Classification quality depends on the local model's capability — `lint` will catch fabrications regardless.

---

## Prior art & credit

The two ideas this tool stands on:

- **Pre-mortem** — Gary Klein, *"Performing a Project Premortem,"* Harvard Business Review, September 2007. The team-strategic version of the idea.
- **The Winchester defense** — originally a quant-finance discipline: *kill criteria must be declared before the run, and cannot be relaxed after.* Used here to argue that `lint` must mechanically verify citations at gate time, not rely on the model's self-report. See omega-lock's [`docs/methodology.md § Kill criteria`](https://github.com/hibou04-ops/omega-lock/blob/main/src/omega_lock/kill_criteria.py) for the parameter-calibration analog.

The naming is explicit: *postmortem* (after death) → *antemortem* (before death). The methodology emerged during the `omega_lock.audit` submodule build in April 2026 and was documented in [hibou04-ops/Antemortem](https://github.com/hibou04-ops/Antemortem).

---

## Status & roadmap

v0.4.0 is **alpha**. The CLI contract (three commands, flags, exit codes) is stable. The JSON artifact schema is additive within v0.4.x — v0.4 introduces `critic_results`, `decision`, `decision_rationale`, and optional per-finding `confidence` / `remediation` / `severity`; all are non-breaking for v0.3.x callers and v0.3.x artifacts still validate unchanged. Prompt iteration continues on both the classifier and the critic as classification-quality data accumulates on diverse real repos — expect v0.4.x bumps for prompt revisions, tracked in CHANGELOG under *"Prompt revisions."* A breaking schema change would cut a v0.5.

Semver applies strictly from v1.0.

**Shipped**
- **v0.2** — scaffold (`init`), classify (`run` against Claude Opus 4.x), lint (schema + disk-verified citations). The foundational three-command CLI surface.
- **v0.3** — `LLMProvider` Protocol and `providers/` package; Anthropic and OpenAI adapters using each vendor's strongest native schema-enforcement path; any OpenAI-compatible endpoint via `--base-url` (Azure, Groq, Together.ai, OpenRouter, local Ollama).
- **v0.4** — `--critic` asymmetric second-pass review (downgrades only); four-level decision gate (`SAFE_TO_PROCEED` / `PROCEED_WITH_GUARDS` / `NEEDS_MORE_EVIDENCE` / `DO_NOT_PROCEED`); optional per-finding `severity` / `remediation` / `confidence`. 111 tests, zero live API calls in CI.

**v0.4.x (prompt iteration track)**
- Dogfood on diverse real repos (Python, TypeScript, Go). Tune the anti-patterns list where classification errors cluster, and tune the critic's sensitivity where it over-weakens honest REAL findings.
- Record a reference classification-quality benchmark so prompt revisions are measured, not guessed. The same benchmark drives the critic-pass cost/benefit numbers — *"how often does a critic call flip a decision level?"* must be an answerable question.

**v0.5 (tooling depth)**
- Reasoning-effort passthrough on the OpenAI adapter for `o1` / `o3`-class models.
- `antemortem diff` — compare two runs on the same doc, surface what classifications moved, which critic statuses changed, whether the decision level shifted.
- Second `cache_control` breakpoint on the files block for iterative same-repo runs.
- Official GitHub Action for CI lint gating.

**v1.0 (contract lock)**
- Public schema versioning (`antemortem.schema.json` published separately).
- Semver guarantees on output JSON shape, decision enum, and exit-code contract.
- HTML renderer for the JSON artifact (printable debrief view).

**Explicitly out of scope** (v0.4 and beyond): web dashboard, database-backed history, multi-user tenancy, proprietary hosting.

Full changelog: [CHANGELOG.md](CHANGELOG.md).

---

## Design principles, in one page

The whole tool in one page, if you only read one section:

1. **You enumerate first, the model reads second.** Anchoring is the failure mode most "plan-review" workflows bake in on the first turn. `antemortem init` gives you the scaffold; you fill in spec + traps + files *before* the LLM sees anything. That ordering is the defense, not a style preference.
2. **A citation the `lint` can't verify is not evidence.** Structured-output APIs parse malformed JSON as "parse error"; they do not catch a line number that's off by seven. The mechanical check — load the file, check bounds — is the only defense. It is a first-class command, not a `--strict` flag.
3. **UNRESOLVED is a valid outcome.** A fabricated line number is strictly worse than an honest *"no evidence in the provided files."* The system prompt is explicit about this, and the discipline rewards it.
4. **The second pass can only downgrade.** `--critic` is asymmetric by construction: CONFIRMED / WEAKENED / CONTRADICTED / DUPLICATE can move a finding *toward* UNRESOLVED / GHOST / dropped, never the other way. A symmetric critic would fabricate findings on sampling noise; an asymmetric one is a strict quality multiplier at the cost of one extra call.
5. **The decision is an enum, not a prose recommendation.** `SAFE_TO_PROCEED` / `PROCEED_WITH_GUARDS` / `NEEDS_MORE_EVIDENCE` / `DO_NOT_PROCEED` are what CI whitelists on. Teams pick their own policy over the four levels; the tool does not invent a threshold.
6. **Vendor-neutral interface, vendor-native adapters.** One Protocol method (`structured_complete`). Each provider uses its own strongest native path — Anthropic `messages.parse`, OpenAI `beta.chat.completions.parse`. No client-side regex. Swap providers with a flag.
7. **The markdown is yours, the JSON is the machine's.** The model never edits your markdown. Classifications go to a sibling `.json` file. Parse bugs in either direction cannot corrupt your source artifact.
8. **Dogfood on self-changes.** Every non-trivial edit to this repo goes through `antemortem run` before the diff exists. The case studies in [the methodology repo](https://github.com/hibou04-ops/Antemortem/tree/main/examples) are real ones from this codebase — honest about what each recon missed.

---

## Contributing

Case studies go in a PR under `examples/` in the [Antemortem methodology repo](https://github.com/hibou04-ops/Antemortem) — they are the most valuable contribution and the hardest to produce. The bar is *"every classification cites `file:line`; post-implementation note exists; honest about what the recon missed."*

Tool-level contributions (new CLI flags, schema fields, prompt edits) belong in this repo as PRs against `main`. Attach the antemortem document for the change itself where feasible — we dogfood the tool on its own development.

---

## Citing

```
antemortem-cli v0.4.0 — tooling for the Antemortem pre-implementation reconnaissance discipline.
https://github.com/hibou04-ops/antemortem-cli, 2026.
```

For the underlying methodology:
```
Antemortem v0.1.1 — AI-assisted pre-implementation reconnaissance for software changes.
https://github.com/hibou04-ops/Antemortem, 2026.
```

---

## License

Apache 2.0. See [LICENSE](LICENSE).

## Colophon

Designed, implemented, and shipped solo. Sixteen modules across `commands/` and `providers/` subpackages, 111 tests, zero live API calls in CI. The tool classifies the changes that build it — dogfood is a first-class test surface.
