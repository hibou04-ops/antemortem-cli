# antemortem (CLI) — Easy Start

> The short version, for people who found the main README intimidating.
> Full doc: [README.md](README.md) · 한국어 Easy: [EASY_README_KR.md](EASY_README_KR.md)
> Generated source-of-truth claims: [English](docs/generated/claims.md) · [Korean](docs/generated/claims_kr.md).
> Trust model: [English](docs/trust_model.md) · [Korean](docs/trust_model_kr.md).
> Toolkit positioning: [English](docs/toolkit_positioning.md) · [Korean](docs/toolkit_positioning_kr.md).
> Claim ledger: [English](docs/claim_ledger.md) · [Korean](docs/claim_ledger_kr.md).
> CLI examples: [English](docs/examples.md) · [Korean](docs/examples_kr.md).

## What is this?

Antemortem checks an implementation plan before code exists. You write the spec, the risks you think might happen, and the repo files the model may inspect. It classifies each risk as `REAL`, `GHOST`, `NEW`, or `UNRESOLVED`, then requires citations that `lint` can verify on disk.

Use it before risky refactors, agent-generated patches, implementation-plan merges, or CI gates on large changes.

Ordinary AI review usually starts from a diff or a chat. Antemortem starts earlier: you name the traps first, the model is constrained to listed repo files, and unverified citations fail the toolchain.

## Trust loop

- `doctor`: preview what will be read and sent.
- `run`: write a structured recon artifact.
- `lint`: verify schema, citations, and evidence binding.
- `evidence`: fill missing evidence hashes in existing artifacts.
- `eval`: measure offline golden cases.
- `gate`: enforce the decision policy in CI.

## The 7 commands

```bash
# 1. Scaffold a markdown doc from the template
antemortem init auth-refactor
# → antemortem/auth-refactor.md  (you edit the Spec + Traps + Files sections)

# 2. Preflight before spending a provider call
antemortem doctor antemortem/auth-refactor.md --repo .

# 3. Run the LLM classification
antemortem run antemortem/auth-refactor.md --repo .
# → antemortem/auth-refactor.json  (REAL/GHOST/NEW/UNRESOLVED + file:line + decision)

# 4. Lint (checks citations and evidence hashes on disk)
antemortem lint antemortem/auth-refactor.md --repo .
# Exit 0 = validation passed; Exit 1 = validation failed

# 5. Fill missing local evidence hashes in an existing artifact
antemortem evidence antemortem/auth-refactor.json --repo . --write-missing

# 6. Gate (lint + decision allowlist for CI)
antemortem gate antemortem/auth-refactor.md --repo .
# Default allowed decisions: SAFE_TO_PROCEED, PROCEED_WITH_GUARDS

# 7. Eval (offline golden benchmark harness)
antemortem eval benchmarks/golden_cases --json
```

Optional critic mode: `antemortem run ... --critic` adds a second pass that can only downgrade findings: `CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE`.

## Evidence hashes

Use `antemortem evidence <artifact.json> --repo . --write-missing` to maintain older artifacts that have valid citations but no hashes. Use `antemortem lint <doc.md> --repo . --strict-evidence` in CI to require every non-UNRESOLVED finding to have a current hash.

## Demo replay

```bash
PYTHONIOENCODING=utf-8 python examples/demo_replay.py
antemortem lint examples/demo_antemortem.md --repo .
```

The replay uses stored output. No API key or network call is required.
It prints `REAL`, `GHOST`, `NEW`, `UNRESOLVED`, the final decision, and lint verification; `tests/test_demo_replay.py` checks that this README command still matches the stored demo output.

## Release check

```bash
python scripts/release_audit.py
```

This is a local readiness check. It builds and runs `twine check`, but it does not publish.

CI runs the same offline trust checks and a separate wheel smoke job. It does not need provider API keys.

To test the installed wheel entrypoint:

```bash
python scripts/smoke_wheel_install.py
```

## Exit codes

Stable exit codes are documented in [CLI Exit Codes](docs/cli_exit_codes.md): `0` success, `1` validation failure, `2` usage/configuration error, `3` provider failure, `4` policy gate failure, `70` reserved internal error.

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

OpenAI-compatible endpoints that implement the OpenAI structured `parse` path use:
```bash
antemortem run foo.md --repo . --provider openai --base-url https://... --model ...
```
Local and partially compatible endpoints still need `antemortem lint`; structured-output fidelity varies by model.

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
- **Every classification carries a `file:line` citation.** Pydantic-enforced at the SDK boundary. `antemortem lint` re-verifies every citation against disk line bounds and verifies `evidence_hash` / `evidence_snippet` when present.

Without both, the result is an unverified plan review. With both, it is a mechanical screening step.

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

antemortem doctor antemortem/my-change.md --repo .
# Shows parsed traps, files to read, missing/excluded files, payload size, and readiness.

antemortem run antemortem/my-change.md --repo .
# Reads the listed files from your repo, classifies each trap.

antemortem lint antemortem/my-change.md --repo .
# Re-verifies every file:line and evidence binding against disk.

antemortem evidence antemortem/my-change.json --repo . --write-missing
# Fills missing hashes only; mismatches are reported, not overwritten.

antemortem gate antemortem/my-change.md --repo .
# Fails CI if lint fails or the decision is outside the allowlist.
```

## Go deeper

- Full CLI docs + flags: [README.md](README.md)
- The methodology itself (this CLI is a wrapper): [Antemortem repo](https://github.com/hibou04-ops/Antemortem)
- Schema definitions: `src/antemortem/schema.py`
- Decision gate rules: `src/antemortem/decision.py`

License: Apache 2.0. Copyright (c) 2026 hibou.
