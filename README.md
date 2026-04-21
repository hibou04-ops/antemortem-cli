# antemortem-cli

[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![PyPI](https://img.shields.io/badge/pypi-0.2.0-blue.svg)](https://pypi.org/project/antemortem/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](#status)
[![Tests](https://img.shields.io/badge/tests-68%20passing-brightgreen.svg)](tests/)
[![Methodology](https://img.shields.io/badge/methodology-Antemortem-blueviolet.svg)](https://github.com/hibou04-ops/Antemortem)

> **Pre-implementation reconnaissance for software changes.**
> Stress-test your plan against the actual code *before* you write the diff. Fifteen minutes. File-and-line citations. A Pydantic schema that fails the lint if anything's fabricated.

```bash
pip install antemortem
```

---

## Why this exists

Most nontrivial changes start the same way: you write a few paragraphs of spec, guess at three or four things that might go wrong, open a PR, and then burn half a day discovering that one of your "risks" was imaginary and one you never imagined was load-bearing. Code review catches what's *on* the diff. Tests catch what you thought to test. Neither helps with the category of mistake the author has already baked into the plan.

An **antemortem** is the recon you run *before* the first keystroke. You enumerate your own traps on paper, hand the plan and the implicated files to an LLM, and for each trap get back exactly one of:

| Label | Meaning | What the model must cite |
|---|---|---|
| `REAL` | Code confirms the risk. Unless mitigated, the change breaks or regresses. | `file:line` of the failure-inducing code. |
| `GHOST` | Code contradicts the risk. The feared behavior doesn't happen, or an existing mitigation already handles it. | `file:line` of the disproving evidence. |
| `NEW` | A risk the model surfaced that wasn't on your list. | `file:line` of the code that raises it. |
| `UNRESOLVED` | No evidence in the provided files either way. Honest, not a failure. | `null` (but explanation required). |

Two guardrails keep this from collapsing into "ask an LLM to review my plan":

1. **You enumerate before the model sees the code.** Prevents anchoring on the model's framing.
2. **Every non-UNRESOLVED classification must carry a `file:line` citation.** Enforced as a Pydantic schema field in the API call, then re-verified on disk by the `lint` command. Hallucinated line numbers fail the build.

The discipline itself is documented at [`hibou04-ops/Antemortem`](https://github.com/hibou04-ops/Antemortem). **This repo is the tool that runs it.**

---

## 30-second demo

```bash
$ antemortem init auth-refactor
Created antemortem/auth-refactor.md (basic template)

# (fill in spec, traps, and the files list...)

$ antemortem run antemortem/auth-refactor.md --repo .
Reading 4 file(s) from . ...
Calling Claude (this can take 30-90s for multi-file recon) ...
Classified 5 traps (2 GHOST, 2 REAL, 1 UNRESOLVED); surfaced 1 new trap(s)
Artifact: antemortem/auth-refactor.json
Tokens: 231 input (+4812 cached read, +0 cached write), 1847 output

$ antemortem lint antemortem/auth-refactor.md --repo .
PASS - auth-refactor.md validates clean (schema + classifications)
```

That last `lint` line is the point. Every citation was parsed, every `file:line` was verified to exist in `--repo`, every range was checked against the file's line count. No hallucinations reached the spec.

---

## The three commands

### `antemortem init <name>`

Scaffolds a document from the official template. YAML frontmatter (name, date, scope, reversibility, status, template) plus a seven-section body. `--enhanced` swaps to the richer template: calibration dimensions (evidence strength, blast radius, reversibility), fine-grained classification subtypes (REAL-structural, GHOST-mitigated, NEW-spec-gap, ...), an explicit skeptic pass on every REAL/NEW finding, and a decision-first output structure.

```bash
antemortem init my-feature                  # basic
antemortem init prod-migration --enhanced   # for high-stakes changes
```

Templates are vendored from [Antemortem](https://github.com/hibou04-ops/Antemortem) under MIT.

### `antemortem run <doc>`

Parses the document, extracts the spec + traps table + listed files, loads file contents from `--repo`, calls the Anthropic API with a frozen system prompt, and writes the classifications to a JSON audit artifact alongside the markdown (`<doc>.json`).

Concrete design:

| Concern | Choice | Why |
|---|---|---|
| Model | Pinned to a single Anthropic Claude version in code | Classification + multi-file chain tracing is intelligence-sensitive. No model fallback — keeps the prompt contract stable and behavior reproducible across runs. |
| Reasoning | Adaptive thinking enabled, `effort: high` | The model-provided sampling knobs (temperature / top_p / top_k) are removed on the pinned version; prompting replaces them. `high` effort is the vendor's recommended minimum for intelligence-sensitive work. |
| Output format | `messages.parse(output_format=AntemortemOutput)` | Pydantic schema enforcement at the SDK boundary. A malformed response raises `ValidationError` before the CLI can see it. No hand-written JSON parsing on the hot path. |
| Caching | `cache_control={"type": "ephemeral"}` on the system prompt | The system prompt is sized past the pinned model's cacheable-prefix minimum, so repeat runs in the same 5-minute window hit cache at ~0.1× base input cost. The CLI surfaces `cache_read_input_tokens` on every call — silent invalidators fail loud, not silent. |
| File loading | `--repo` root, path-traversal rejected, UTF-8 with replace fallback | A file listed as `../../etc/passwd` gets skipped with a warning, not honored. |

The markdown document itself is **not** modified — the JSON artifact is the machine-readable output. `lint` validates the artifact against disk. This separation means parsing bugs can't corrupt your markdown.

### `antemortem lint <doc>`

Two tiers of validation, composable in CI:

1. **Pre-run (schema)**: frontmatter parses, spec section has text, at least one trap is enumerated, at least one file is listed under Recon protocol. Applies to every document.
2. **Post-run (citations)**: if `<doc>.json` exists next to the document, every input trap has a classification, every classification has a valid `path:line` or `path:line-line` citation, every cited file exists in `--repo`, and every cited line range is within that file's bounds.

Exit `0` on pass, `1` on fail, with every violation printed on its own line. Plug into CI as the gate: *"no PR merges unless its antemortem lints clean."*

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
│  api.py -> client.messages.parse()                           │
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
│  citations.py -> verify every path:line on disk              │
│  exit 0 = trust the classifications                          │
│  exit 1 = something is fabricated or out of date             │
└──────────────────────────────────────────────────────────────┘
```

Every module has a single responsibility; the pipeline is testable end-to-end without the network. `AntemortemDocument`, `Classification`, `NewTrap`, and `AntemortemOutput` are the data contract — the same types flow from `run` to `lint`, so a drift in one is caught in the other.

---

## Design decisions worth defending

**Single model pin, no fallback.** Multi-model "support" is vaporware at v0.2. The system prompt, the schema, the effort level, and the expected behavior of adaptive thinking are all model-specific contracts. Dropping in a different vendor's model would require re-tuning every one. v0.3 might add a model selector once the contract stabilizes; until then, pinning is honest.

**Citations verified on disk by `lint`, not trusted.** Structured-output APIs can break schema conformance under refusal, and even well-behaved models occasionally miscount lines in long files. The *only* defense is re-verification against the source. This is why `lint` is a first-class command rather than a flag.

**JSON artifact is the output, markdown is the input.** The model could edit the markdown in place — some tools do that. We don't, for three reasons: (1) the markdown is yours, not the model's; (2) a parse bug in either direction could corrupt hours of work; (3) machine-readable JSON composes cleanly with downstream tooling (CI gates, dashboards, diff viewers). The markdown stays a human artifact.

**Substantial system prompt, deliberately.** The pinned model caches any prefix over its cacheable-prefix minimum at ~0.1× read cost. A shorter prompt wouldn't cache; a longer one would drift from the discipline it enforces. Every substantive byte is load-bearing: role framing, input format, four labels with exact definitions, citation rules with good/bad examples, anti-patterns list, scope boundary, four few-shot examples. [The full prompt](src/antemortem/prompts.py) is worth reading as a case study in prompt-cache-aware design.

**Pydantic v2 schemas are the data contract, not dict-shaped comments.** `Classification`, `NewTrap`, `AntemortemOutput`, `Frontmatter`, `AntemortemDocument` all flow end-to-end: the SDK validates on the API boundary, `run` writes validated JSON, `lint` validates on load. A malformed classification never gets written to disk.

**Windows path normalization is cache-invariant, not cosmetic.** `src\foo.py` and `src/foo.py` render the same on disk but are different bytes in the API payload, which breaks prompt caching. Every path is normalized to forward slashes before the content is built. See `api.py:_build_user_content`.

**`run` exits 2 without `ANTHROPIC_API_KEY`, not 1.** Exit codes are a contract with CI systems: `1` = content problem (fixable by the user), `2` = environment problem (fixable by the operator). Mixing them makes CI triage harder.

**Scope boundary is enforced, not suggested.** The system prompt explicitly says *"You classify what is in the provided files. You do not: speculate about files not shown, comment on architecture beyond the spec's scope, recommend the user adopt a different design, evaluate whether the change is a good idea."* If the user asks for any of those, the model is instructed to note it in `spec_mutations` as "Out of antemortem scope" and proceed. The tool does one thing.

---

## Cost & performance

Per-`run` cost at current Anthropic frontier-model pricing, estimated on typical workloads:

| Scenario | Cache behavior | Est. cost |
|---|---|---|
| First run of the day | System prompt written to cache (write premium) | ~\$0.15–0.20 |
| Subsequent run within 5 min on same prompt | System prompt read from cache (~0.1×) | ~\$0.10–0.12 |
| 100 iteration runs during active development | Mix of writes + reads | \$10–20 |

Actual cost will vary by model tier and repository size. Every `run` prints the token breakdown — `input (+cache_read, +cache_write) output` — so the cache engaging (or silently failing) is visible on each invocation. If `cache_read_input_tokens` is zero across consecutive runs with an unchanged prompt, that is a silent invalidator somewhere in the prompt-building pipeline and the CLI prints an explicit warning. [See the rationale](src/antemortem/api.py) in `api.py`.

The default `--max-tokens` is 16000, with typical output landing in the 1–4k range. Raising it is supported up to 128000 for the rare deep recon on a large surface.

---

## Validation

**68 tests, 0 network calls.** The Anthropic client is accepted via a `Protocol` interface in `api.py`, which means every API test mocks the response with `SimpleNamespace` or `MagicMock`. This buys two things: deterministic CI that doesn't burn API credits, and test-time freedom to assert the *exact* shape of the request payload (model, thinking config, cache_control placement, sorted file order) without negotiating with a real server.

Test surface:

| Module | Coverage |
|---|---|
| `schema.py` | 9 tests — required fields, label enum, citation-nullable on UNRESOLVED, NewTrap id pattern, JSON roundtrip. |
| `citations.py` | 13 tests — range parsing, Windows backslash normalization, empty-string / prose / zero-line / reversed-range rejection, disk verification including path traversal. |
| `parser.py` | 12 tests — frontmatter validation, section extraction, recon-vs-pre-recon disambiguation, trap-table parsing with placeholder-row filtering. |
| `lint.py` | 11 tests — both tiers (schema-only and artifact), every violation path, exit codes. |
| `api.py` | 5 tests — payload shape, file sorting determinism, refusal branch, parsed-output contract, dict-fallback coercion. |
| `run.py` | 7 tests — full flow with mocked client, error paths, warnings, JSON-summary env var. |
| `init.py` | 6 tests — basic + enhanced templates, `--force`, path traversal rejection, ISO date frontmatter. |
| `cli.py` | 5 tests — `--help`, `--version`, no-args-prints-help. |

Run with `uv run pytest -q`. Typical wall time: 0.2s.

---

## The 3-layer stack

This CLI does not exist in isolation. It is the third tier of a layered discipline:

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

- **[omega-lock](https://github.com/hibou04-ops/omega-lock)** is the Python calibration framework that the Antemortem discipline was *first practiced on*. Its `omega_lock.audit` submodule was built using a 15-minute antemortem recon that caught one ghost trap and downgraded three risks before implementation began.
- **[Antemortem](https://github.com/hibou04-ops/Antemortem)** is the methodology that crystallized from that build: the seven-step protocol, the basic and enhanced templates, the first case study. Docs-only.
- **antemortem-cli** (this repo) is the tooling that removes the friction: scaffold with `init`, classify with `run`, verify with `lint`. Three commands, one data contract, disk-verified citations.

The layering matters for correctness: the methodology was validated by a real shipped artifact *before* the CLI was built, so the tool is automating a protocol that is already known to work — not a protocol invented alongside the tool.

---

## Case study: the ghost trap

Before the `omega_lock.audit` submodule was built, seven risks were on the list. A 15-minute antemortem recon, with the model citing `file:line` on every classification, produced:

- **One ghost.** Trap #1 was *"WalkForward folds internally, so the audit decorator will double-count evaluation cost."* The model cited `src/omega_lock/walk_forward.py:82` — a single `return self._evaluate(params)` with no surrounding loop. The feared fold didn't exist. ≈0.5 engineer-day saved.
- **Three risk downgrades.** JSON serialization, memory blow-up on large candidate sets, and iterative-round bookkeeping all had existing mitigations in the codebase. Each dropped from 30–40% P(issue) to 10–15%.
- **One new requirement.** The model noticed `Target` was used in three different roles (searcher, evaluator, renderer) in the same flow and recommended a `target_role` field on the spec before implementation. Accepted; avoided an ambiguity that would have surfaced mid-implementation.

Post-recon `P(full spec ships on time)` went from 55–65% to 70–78%. The implementation took one engineer-day. Twenty new tests passed on first run.

The full write-up is [`examples/omega-lock-audit.md`](https://github.com/hibou04-ops/Antemortem/blob/main/examples/omega-lock-audit.md) in the Antemortem repo, including an honest post-implementation note on what the recon missed (a Windows cp949 em-dash terminal encoding issue that surfaced at runtime — antemortems don't catch platform encoding issues, which is [now listed under Limits in methodology.md](https://github.com/hibou04-ops/Antemortem/blob/main/docs/methodology.md#limits)).

---

## Status

v0.2.0 is **alpha**. The CLI contract (three commands, their flags, their exit codes) is stable. The prompt will iterate as classification-quality data accumulates on diverse real repos — expect v0.2.x bumps for prompt revisions, tracked in CHANGELOG under *"Prompt revisions"*. The JSON artifact schema is stable within v0.2.x; breaking schema changes would cut a v0.3.

Semver applies strictly from v1.0.

Full changelog: [CHANGELOG.md](CHANGELOG.md).

---

## Roadmap

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

**Explicitly out of scope** (v0.2 and beyond): web dashboard, database-backed history, multi-user tenancy, proprietary hosting. antemortem is a local developer tool; keep it local.

---

## Contributing

Case studies go in a PR under `examples/` in the [Antemortem methodology repo](https://github.com/hibou04-ops/Antemortem) — they're the most valuable contribution and the hardest to find. The bar is *"every classification cites `file:line`; post-implementation note exists; honest about what the recon missed."*

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
