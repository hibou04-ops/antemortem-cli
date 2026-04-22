# antemortem (CLI) — Easy Start

> The short version, for people who found the main README intimidating.
> Full doc: [README.md](README.md) · 한국어 Easy: [EASY_README_KR.md](EASY_README_KR.md)

## What is this?

A 3-command CLI that runs the [Antemortem methodology](https://github.com/hibou04-ops/Antemortem) for you — scaffold a risk doc, classify your traps against real code (via an LLM with structured output), and lint the result so you can trust the citations.

Fifteen minutes per change. A machine-readable artifact you can gate CI on.

## The 3 commands (that's the whole API)

```bash
# 1. Scaffold a markdown doc from the template
antemortem init auth-refactor
# → antemortem/auth-refactor.md  (you edit the Spec + Traps + Files sections)

# 2. Run the LLM classification
antemortem run antemortem/auth-refactor.md --repo .
# → antemortem/auth-refactor.json  (REAL/GHOST/NEW/UNRESOLVED + file:line + decision)

# 3. Lint (checks every file:line citation exists on disk)
antemortem lint antemortem/auth-refactor.md --repo .
# Exit 0 = trustworthy; Exit 1 = a citation lies
```

Optional 4th form: `antemortem run ... --critic` adds a second adversarial pass that can only **downgrade** findings (CONFIRMED / WEAKENED / CONTRADICTED / DUPLICATE). ~2× cost, catches LLM over-confidence.

## Install

```bash
pip install antemortem
```

PyPI name is `antemortem` (not `antemortem-cli`). Python 3.11+.

## API keys

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # for --provider anthropic (default: claude-opus-4-7)
export OPENAI_API_KEY=sk-...            # for --provider openai   (default: gpt-4o)
```

OpenAI-compatible endpoints (Azure, Groq, Together, OpenRouter, Ollama) work via:
```bash
antemortem run foo.md --repo . --provider openai --base-url https://... --model ...
```

## What you get back

A JSON artifact with four parts:

1. **Classifications** — one per trap you listed. `REAL` (code confirms), `GHOST` (code disproves), `NEW` (LLM found it), `UNRESOLVED` (no evidence either way). Each with a `file:line` citation, a 1–2 sentence note, optional severity + remediation.
2. **New traps** — risks the LLM surfaced that you didn't list.
3. **Spec mutations** — concrete edits to your spec the recon recommends.
4. **Decision gate** — one of:
   - `SAFE_TO_PROCEED` — no REAL findings
   - `PROCEED_WITH_GUARDS` — REAL findings exist, all have remediation
   - `NEEDS_MORE_EVIDENCE` — ≥50% UNRESOLVED, or REAL findings missing remediation
   - `DO_NOT_PROCEED` — any high-severity REAL/NEW without remediation, or critic contradicted a finding

CI gates on the enum. Humans read the rationale.

## Two guardrails that make this honest

- **You enumerate traps *before* the model sees any code.** Template-enforced. The LLM doesn't get to frame your risk list.
- **Every classification carries a `file:line` citation.** Pydantic-enforced at the SDK boundary. `antemortem lint` re-verifies every citation against disk line counts — hallucinated ranges fail the build.

Without both, you've just asked Claude to vibe-check your plan. With both, it's a mechanical 15-minute screening step.

## When NOT to use it

- Trivial changes (typo, one-line config, docstring).
- No spec yet — write the spec first, *then* antemortem it.
- You've lived in the code for months and already know the answers.
- Build time < recon time.

## One-minute demo flow

```bash
antemortem init my-change
# Edit antemortem/my-change.md:
#   - Fill the "Spec" section
#   - Add at least 1 row to the Traps table
#   - List at least 1 file under "Recon protocol"

antemortem run antemortem/my-change.md --repo .
# Reads the listed files from your repo, classifies each trap.

antemortem lint antemortem/my-change.md --repo .
# Re-verifies every file:line against disk. Exit 0 = you can trust the report.
```

## Go deeper

- Full CLI docs + flags: [README.md](README.md)
- The methodology itself (this CLI is a wrapper): [Antemortem repo](https://github.com/hibou04-ops/Antemortem)
- Schema definitions: `src/antemortem/schema.py`
- Decision gate rules: `src/antemortem/decision.py`

License: Apache 2.0. Copyright (c) 2026 hibou.
