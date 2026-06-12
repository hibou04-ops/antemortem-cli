# antemortem — Easy Start

> The short version, for people who found the main README intimidating.

[![PyPI](https://img.shields.io/pypi/v/antemortem?color=blue&label=pypi&cacheSeconds=3600)](https://pypi.org/project/antemortem/)

README family: [English](README.md) · [한국어](README_KR.md) · [Easy](EASY_README.md) · [쉬운 한국어](EASY_README_KR.md)
Deep docs: generated claims [English](docs/generated/claims.md) · [한국어](docs/generated/claims_kr.md) · trust model [English](docs/trust_model.md) · [한국어](docs/trust_model_kr.md) · toolkit positioning [English](docs/toolkit_positioning.md) · [한국어](docs/toolkit_positioning_kr.md) · claim ledger [English](docs/claim_ledger.md) · [한국어](docs/claim_ledger_kr.md)

## What is this?

Your AI coding agent writes a plan and tells you it's safe against your repo. You have no quick way to know if it actually read the code or just sounded confident. `antemortem` is that check.

You write down the risks you're worried about. The model classifies each one against your real files and has to cite a `file:line` for every answer. Then a separate offline step re-reads each cited line on disk. If a citation is made up, the check fails — loudly. The model's confidence never decides anything; the disk does.

The name says the method. A *post*-mortem asks why something already broke. An *antemortem* runs the autopsy *before* your change is even written — on the plan, while changing course is still cheap.

## Install

```bash
pip install antemortem
```

The PyPI name is `antemortem` (not `antemortem-cli`). Python 3.11+.

## Try it in 30 seconds — no API key

The bundled demo replays a real recon from stored output, so no key and no network are needed. The `lint` at the end is the real offline check:

```bash
git clone https://github.com/hibou04-ops/antemortem-cli.git
cd antemortem-cli && pip install -e ".[mcp]"

# 4 risks → REAL / GHOST / NEW / UNRESOLVED → a decision (pre-recorded, offline)
PYTHONIOENCODING=utf-8 python examples/demo_replay.py

# now machine-verify every file:line and evidence hash against disk
antemortem lint examples/demo_antemortem.md --repo .
```

`lint` exits `0` if every citation checks out on disk and `1` if any is fabricated or stale. That single exit code is the whole idea: a deterministic, offline answer to "did the AI lie about the codebase?"

## The commands

There are **9 commands**. You only need a few to start; the rest are for CI and reporting.

- `antemortem init <name>` — make a recon document from a template. You fill in the spec, the risks ("traps"), and the files to inspect.
- `antemortem doctor <doc>` — preflight: shows what will be read and sent, no API call.
- `antemortem run <doc>` — one provider call. Classifies each risk as `REAL` / `GHOST` / `NEW` / `UNRESOLVED` with a `file:line` citation, and writes a JSON artifact.
- `antemortem lint <doc>` — re-verify every citation against disk, offline. This is the honesty check.
- `antemortem evidence <artifact>` — fill or check evidence hashes in an existing artifact, no provider call.
- `antemortem gate <doc>` — run `lint`, then enforce a decision allowlist. This is what you put in CI.
- `antemortem eval <cases>` — score offline golden benchmark cases.
- `antemortem metrics <artifact>` — print how often the model cited real evidence vs fabricated it: a verified / fabricated count and a fabrication rate. Add `--fail-over 0` to fail CI on any made-up citation.
- `antemortem report <artifact>` — render the run into a shareable Markdown or HTML scorecard you can attach to a PR.

A typical first run:

```bash
antemortem init my-change
# edit antemortem/my-change.md: the Spec, your Traps, and the Files to read
antemortem doctor antemortem/my-change.md --repo .
antemortem run    antemortem/my-change.md --repo .
antemortem lint   antemortem/my-change.md --repo .
antemortem gate   antemortem/my-change.md --repo .
```

## What the decision means

Every run ends in one of four verdicts, and CI can branch on it:

- `SAFE_TO_PROCEED` — no real risks remain.
- `PROCEED_WITH_GUARDS` — real risks exist, but each has a remediation.
- `NEEDS_MORE_EVIDENCE` — too much is unresolved, or citations didn't hold.
- `DO_NOT_PROCEED` — a high-severity risk with no mitigation.

Exit codes are stable: `0` pass, `1` validation/citation failure, `2` usage error, `3` provider failure, `4` policy gate blocked (`70` is reserved for internal errors).

## Providers

Adapters ship for `anthropic`, `openai`, `gemini`, and `ollama`. Ollama runs locally and needs **no API key** — handy for trying it without signing up:

```bash
export ANTHROPIC_API_KEY=sk-ant-...                  # or OPENAI_API_KEY / GEMINI_API_KEY
antemortem run antemortem/my-change.md --repo . --provider ollama   # local, no key
```

The CLI is model-agnostic — pass `--model` to pin any model. Any OpenAI-compatible endpoint works via `--provider openai --base-url <url>`.

## Letting your agent check its own work

You can run `antemortem-mcp` so your AI assistant (Claude Code, Cursor) can call `scaffold` / `run` / `lint` on its own plan before asking you to merge. Setup is one config paste — see [docs/MCP.md](docs/MCP.md) for the details.

And to fail a pull request when citations don't check out, add one line — `antemortem gate ...` — to your CI, or use the bundled GitHub Action. See [docs/GITHUB_ACTION.md](docs/GITHUB_ACTION.md).

## Two guardrails that make this honest

- **You write the risks before the model sees any code.** The model never gets to frame your risk list, so it can't quietly agree with itself and call that a review.
- **Every answer carries a `file:line` citation, re-checked on disk.** A fabricated citation fails the run. The model's confidence is irrelevant — only the disk decides.

Asking your agent to review its own plan has no answer key; antemortem is the answer key, checked by a program.

## When NOT to use it

- Trivial changes (typo, one-line config, version bump).
- No spec yet — write the spec first, then antemortem it.
- Hot-fixes where speed beats discipline, or code you already know cold.

It validates your *plan against existing code* — it won't catch runtime bugs outside the files, and it doesn't replace code review, tests, or design review. It's the cheap screening step that runs *before* them. Where it sits in the wider toolkit is mapped in [docs/toolkit_positioning.md](docs/toolkit_positioning.md) ([한국어](docs/toolkit_positioning_kr.md)).

## Go deeper

- Full front page and every flag: [README.md](README.md)
- What it does and does not verify: [docs/trust_model.md](docs/trust_model.md) ([한국어](docs/trust_model_kr.md))
- The methodology this CLI wraps: [Antemortem](https://github.com/hibou04-ops/Antemortem)

License: Apache 2.0. Copyright (c) 2026 Kyunghoon Gwak.
