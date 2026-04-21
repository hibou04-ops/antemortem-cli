# antemortem-cli

[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![PyPI](https://img.shields.io/badge/pypi-0.2.0-blue.svg)](https://pypi.org/project/antemortem/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](#status)
[![Tests](https://img.shields.io/badge/tests-68%20passing-brightgreen.svg)](tests/)
[![Methodology](https://img.shields.io/badge/methodology-Antemortem-blueviolet.svg)](https://github.com/hibou04-ops/Antemortem)

> **Your next feature has seven risks. Five are imaginary. Two you haven't named yet.**
>
> An antemortem finds out which is which — from the code, in fifteen minutes, with file-and-line citations the lint can verify. Before you write the diff.

```bash
pip install antemortem
```

한국어 README: [README_KR.md](README_KR.md)

---

## Table of Contents

- [The failure mode this solves](#the-failure-mode-this-solves)
- [Worked example: a real ghost trap](#worked-example-a-real-ghost-trap)
- [The three commands](#the-three-commands)
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

Templates are vendored from [Antemortem](https://github.com/hibou04-ops/Antemortem) under MIT.

### `antemortem run <doc>`

Parses the document, extracts the spec + traps table + listed files, loads file contents from `--repo`, calls the Anthropic API with a frozen system prompt, and writes the classifications to a JSON audit artifact alongside the markdown (`<doc>.json`).

| Concern | Choice | Why |
|---|---|---|
| Model | A single Claude version pinned in code | Classification + multi-file chain tracing is intelligence-sensitive. No model fallback — keeps the prompt contract stable and behavior reproducible across runs. |
| Reasoning | Adaptive thinking, `effort: high` | Sampling knobs (`temperature` / `top_p` / `top_k`) are removed on the pinned model; prompting replaces them. `high` effort is the vendor's recommended minimum for intelligence-sensitive work. |
| Output format | `messages.parse(output_format=AntemortemOutput)` | Pydantic schema enforcement at the SDK boundary. A malformed response raises `ValidationError` before the CLI sees it. No hand-written JSON parsing on the hot path. |
| Caching | `cache_control={"type": "ephemeral"}` on the system prompt | The ~5k-token system prompt is sized past the pinned model's cacheable-prefix minimum so repeat runs in the same 5-minute window hit cache at ~0.1× base input cost. The CLI surfaces `cache_read_input_tokens` on every call — silent invalidators fail loud, not silent. |
| File loading | `--repo` root, path-traversal rejected, UTF-8 with replace fallback | A file listed as `../../etc/passwd` gets skipped with a warning, not honored. |

The markdown document itself is **not** modified. The JSON artifact is the machine-readable output. `lint` validates the artifact against disk. This separation means parsing bugs can't corrupt your markdown.

### `antemortem lint <doc>`

Two tiers of validation, composable in CI:

1. **Pre-run (schema)**: frontmatter parses, spec section has text, at least one trap is enumerated, at least one file is listed under Recon protocol. Applies to every document.
2. **Post-run (citations)**: if `<doc>.json` exists next to the document, every input trap has a classification, every classification has a valid `path:line` or `path:line-line` citation, every cited file exists in `--repo`, and every cited line range is within that file's bounds.

Exit `0` on pass, `1` on fail, with every violation printed on its own line. Plug into CI as the merge gate: *"no PR merges unless its antemortem lints clean."*

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

# ↓ run.py → api.py → messages.parse(output_format=AntemortemOutput)
AntemortemOutput(
    classifications=[
        Classification(
            id="t1",
            label="REAL",
            citation="src/auth/middleware.py:45-52",
            note="The refresh path (line 48) issues a new token but leaves the old session cookie untouched.",
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
        ),
    ],
    spec_mutations=[
        "Add: on token rotation, explicit invalidation of the old session cookie.",
        "Add: CDN cache-invalidation step in the rotation sequence.",
    ],
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
│  api.py → client.messages.parse()                            │
│    thinking: adaptive, effort: high                          │
│    system=[SYSTEM_PROMPT + cache_control: ephemeral]         │
│    output_format=AntemortemOutput                            │
└────────────────┬─────────────────────────────────────────────┘
                 │  SDK validates response against schema
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  AntemortemOutput                                            │
│    classifications[]  (id, label, citation, note)            │
│    new_traps[]        (hypothesis, citation, note)           │
│    spec_mutations[]   (free-form edits to your spec)         │
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

Every module has a single responsibility; the pipeline is testable end-to-end without the network. `AntemortemDocument`, `Classification`, `NewTrap`, and `AntemortemOutput` are the data contract — the same types flow from `run` to `lint`, so a drift in one is caught in the other.

---

## Design decisions worth defending

**Single model pin, no fallback.** Multi-model "support" at v0.2 would be vaporware. The system prompt, the schema, the effort level, and the expected behavior of adaptive thinking are all model-specific contracts. Dropping in a different vendor's model would require re-tuning every one. The pin is honest until v0.3's `--model` flag arrives with validation that the alternative survives the prompt contract.

**Citations verified on disk by `lint`, not trusted.** Structured-output APIs can break schema conformance under refusal, and even well-behaved models occasionally miscount lines in long files. Trusting the model's self-reported citations is the same mistake as trusting a tested pull request is bug-free. The *only* defense is re-verification against the source. `lint` is a first-class command, not a `--strict` flag, because CI gates need to run it without ceremony.

**JSON artifact is the output, markdown is the input.** The model could edit the markdown in place — some tools do that. We don't, for three reasons: (1) the markdown is yours, not the model's; (2) a parse bug in either direction could corrupt hours of work; (3) machine-readable JSON composes cleanly with downstream tooling (CI gates, dashboards, diff viewers). The markdown stays a human artifact.

**~5k-token system prompt, deliberately.** The pinned model caches any prefix over its cacheable-prefix minimum at ~0.1× read cost. A shorter prompt wouldn't cache; a longer one would drift from the discipline it enforces. Every substantive byte is load-bearing: role framing, input format, four labels with exact definitions, citation rules with good/bad examples, anti-patterns list, scope boundary, four few-shot JSON examples. [The full prompt](src/antemortem/prompts.py) is worth reading as a case study in prompt-cache-aware design.

**Pydantic v2 schemas are the data contract, not dict-shaped comments.** `Classification`, `NewTrap`, `AntemortemOutput`, `Frontmatter`, `AntemortemDocument` all flow end-to-end: the SDK validates on the API boundary, `run` writes validated JSON, `lint` validates on load. A malformed classification never gets written to disk, which means it never gets merged into main.

**Windows path normalization is cache-invariant, not cosmetic.** `src\foo.py` and `src/foo.py` render the same on disk but are different bytes in the API payload — the cache key is byte-exact. Every path is normalized to forward slashes before content is built. See `api.py:_build_user_content`. This is a 3-line fix that would silently waste ~\$15/100 runs if missed.

**`run` exits 2 without `ANTHROPIC_API_KEY`, not 1.** Exit codes are a contract with CI systems: `1` = content problem (fixable by the user, "my antemortem has issues"), `2` = environment problem (fixable by the operator, "the secret is missing"). Mixing them makes CI triage harder.

**Scope boundary is enforced in the prompt, not suggested.** The system prompt explicitly says: *"You classify what is in the provided files. You do not: speculate about files not shown, comment on architecture beyond the spec's scope, recommend the user adopt a different design, evaluate whether the change is a good idea."* If the user asks for any of those, the model is instructed to note it in `spec_mutations` as "Out of antemortem scope" and proceed. The tool does one thing.

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

Per-`run` cost at current Anthropic frontier-model pricing (typical workload):

| Scenario | Cache behavior | Est. cost |
|---|---|---|
| First run of the day | System prompt written to cache (write premium) | ~\$0.15–0.20 |
| Subsequent run within 5 min on same prompt | System prompt read from cache (~0.1×) | ~\$0.10–0.12 |
| 100 iteration runs during active development | Mix of writes + reads | \$10–20 |

Every `run` prints the token breakdown — `input (+cache_read, +cache_write) output` — so cache engagement (or silent failure) is visible on each invocation. If `cache_read_input_tokens` is zero across consecutive runs with an unchanged prompt, a silent invalidator exists somewhere in the prompt-building pipeline and the CLI prints an explicit warning.

The default `--max-tokens` is 16000. Typical output lands in the 1–4k range. Raising it to 128000 is supported for rare deep-surface recons.

---

## Validation

**68 tests, 0 network calls in CI.** The Anthropic client is accepted via a `Protocol` interface in `api.py`, which means every API test mocks the response with `SimpleNamespace` or `MagicMock`. Two benefits: deterministic CI that doesn't burn API credits, and test-time freedom to assert the *exact* shape of the request payload (model, thinking config, cache_control placement, sorted file order) without negotiating with a real server.

| Module | Coverage |
|---|---|
| `schema.py` | 9 tests — required fields, label enum, citation-nullable on UNRESOLVED, NewTrap id pattern, JSON roundtrip. |
| `citations.py` | 13 tests — range parsing, Windows backslash normalization, empty-string / prose / zero-line / reversed-range rejection, disk verification including path traversal. |
| `parser.py` | 12 tests — frontmatter validation, section extraction, `recon-protocol` vs `pre-recon` disambiguation, trap-table parsing with placeholder-row filtering. |
| `lint.py` | 11 tests — both tiers (schema-only and artifact), every violation path, exit codes. |
| `api.py` | 5 tests — payload shape, file sorting determinism, refusal branch, parsed-output contract, dict-fallback coercion. |
| `run.py` | 7 tests — full flow with mocked client, error paths, warnings, JSON-summary env var. |
| `init.py` | 6 tests — basic + enhanced templates, `--force`, path traversal rejection, ISO date frontmatter. |
| `cli.py` | 5 tests — `--help`, `--version`, no-args-prints-help. |

Run with `uv run pytest -q`. Typical wall time: 0.2s.

---

## The 3-layer stack

This CLI is the third tier of a layered discipline, not a point tool:

```
         ┌─────────────────────────────────────────────┐
 Layer 3 │  antemortem-cli  (this repo)                │  "Practice the discipline"
         │  0.2.0 — CLI + PyPI + schema + lint         │
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

**Why not just ask Claude "review my spec before I code"?**

That is the degenerate case this tool exists to prevent. Without the two guardrails, an LLM happily agrees with whatever you wrote. You get a list of generic risks mixed with genuine ones, no way to tell them apart, and no pressure on the model to back up claims. The `file:line` requirement plus `lint`'s re-verification is the difference between "opinion" and "evidence."

**Won't the model just make up line numbers?**

It sometimes will. That is why `lint` exists. Every citation is parsed, the file is loaded, and the line range is checked against actual file bounds. A hallucinated citation fails the lint. The model is instructed that *"A fabricated line number is strictly worse than UNRESOLVED — UNRESOLVED is honest, fabrication is not,"* and the discipline backs this up with mechanical verification.

**Does this work on closed-source or private code?**

Yes. The LLM reads what you give it; it does not need a public repo. The only constraint is that citations in a published case study should quote enough inline context to be verifiable by readers without repo access.

**What about an IDE plugin? A web UI?**

Out of scope for v0.2. The CLI is the right surface for a CI-gate tool — you can `antemortem lint` in GitHub Actions, pre-commit hooks, or a local Makefile. A web UI would add state and auth; a plugin would couple to one IDE's extension API. Both are worse for the primary use case (merge-gate).

**I'm in Go / Rust / TypeScript. Can I use this?**

Yes. Antemortem is language-agnostic — it reads *files*, not Python ASTs. The CLI is a Python package, but the target repo can be anything. The case study in omega-lock is Python; the discipline works the same way on a Rust crate or a TypeScript monorepo.

**How is this different from Cursor / Claude Code / Aider's "plan" mode?**

Those tools integrate planning into the editing loop — useful, but the plan lives in the same session as the implementation. Antemortem is a *separate artifact* you keep. Six months from now, when the feature surprises you, you can reread `antemortem/auth-refactor.md` and see which of your assumptions broke. It is a disciplined paper trail, not an ephemeral chat.

**Why Python?**

Because the first user was building on omega-lock (Python), and because the Anthropic SDK has the tightest Python ergonomics for structured outputs. The tool is 100% offline-validatable (`lint` doesn't need the network) so Python runtime is not a hot-path constraint.

---

## Prior art & credit

The two ideas this tool stands on:

- **Pre-mortem** — Gary Klein, *"Performing a Project Premortem,"* Harvard Business Review, September 2007. The team-strategic version of the idea.
- **The Winchester defense** — originally a quant-finance discipline: *kill criteria must be declared before the run, and cannot be relaxed after.* Used here to argue that `lint` must mechanically verify citations at gate time, not rely on the model's self-report. See omega-lock's [`docs/methodology.md § Kill criteria`](https://github.com/hibou04-ops/omega-lock/blob/main/src/omega_lock/kill_criteria.py) for the parameter-calibration analog.

The naming is explicit: *postmortem* (after death) → *antemortem* (before death). The methodology emerged during the `omega_lock.audit` submodule build in April 2026 and was documented in [hibou04-ops/Antemortem](https://github.com/hibou04-ops/Antemortem).

---

## Status & roadmap

v0.2.0 is **alpha**. The CLI contract (three commands, flags, exit codes) is stable. The prompt will iterate as classification-quality data accumulates on diverse real repos — expect v0.2.x bumps for prompt revisions, tracked in CHANGELOG under *"Prompt revisions."* The JSON artifact schema is stable within v0.2.x; breaking schema changes would cut a v0.3.

Semver applies strictly from v1.0.

**v0.2.x (prompt iteration track)**
- Dogfood on diverse real repos (Python, TypeScript, Go). Tune anti-patterns list where classification errors cluster.
- Record a reference classification-quality benchmark so prompt revisions are measured, not guessed.

**v0.3 (tooling depth)**
- Second `cache_control` breakpoint on the files block for iterative same-repo runs.
- `antemortem diff` — compare two runs on the same doc, surface what classifications moved.
- HTML renderer for the JSON artifact (printable debrief view).
- Optional `--model` flag once the prompt stabilizes enough to survive a model swap.

**v1.0 (contract lock)**
- Public schema versioning (`antemortem.schema.json` published separately).
- Semver guarantees on output JSON shape.
- Official GitHub Action for CI lint gating.

**Explicitly out of scope** (v0.2 and beyond): web dashboard, database-backed history, multi-user tenancy, proprietary hosting.

Full changelog: [CHANGELOG.md](CHANGELOG.md).

---

## Contributing

Case studies go in a PR under `examples/` in the [Antemortem methodology repo](https://github.com/hibou04-ops/Antemortem) — they are the most valuable contribution and the hardest to produce. The bar is *"every classification cites `file:line`; post-implementation note exists; honest about what the recon missed."*

Tool-level contributions (new CLI flags, schema fields, prompt edits) belong in this repo as PRs against `main`. Attach the antemortem document for the change itself where feasible — we dogfood the tool on its own development.

---

## Citing

```
antemortem-cli v0.2.0 — tooling for the Antemortem pre-implementation reconnaissance discipline.
https://github.com/hibou04-ops/antemortem-cli, 2026.
```

For the underlying methodology:
```
Antemortem v0.1.1 — AI-assisted pre-implementation reconnaissance for software changes.
https://github.com/hibou04-ops/Antemortem, 2026.
```

---

## License

MIT. See [LICENSE](LICENSE).

## Colophon

Designed, implemented, and shipped solo. Seven modules, 68 tests, 0 live API calls in CI. The tool classifies the changes that build it — dogfood is a first-class test surface.
