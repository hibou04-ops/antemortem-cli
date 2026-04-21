# antemortem-cli

![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![Version](https://img.shields.io/badge/version-0.2.0-blue)
![Status](https://img.shields.io/badge/status-alpha-orange)

*CLI for the [Antemortem](https://github.com/hibou04-ops/Antemortem) pre-implementation reconnaissance discipline.*

An antemortem is what you do before you build. You put the planned change under stress *on paper*, use an LLM to read the existing code thoroughly, enumerate traps, classify each as REAL / GHOST / NEW with primary-source `file:line` citations, and revise your risk and your spec before writing a single line. This CLI automates the scaffolding, the classification pass, and the schema lint — so the discipline is a single command, not a workflow you have to remember.

The methodology lives at [hibou04-ops/Antemortem](https://github.com/hibou04-ops/Antemortem). This repo is the tooling that runs it.

## Install

```bash
pip install antemortem
```

Requires Python 3.11+ and an `ANTHROPIC_API_KEY` environment variable for `run`.

## Three commands

### `antemortem init` — scaffold a document

```bash
antemortem init my-feature
# → Created antemortem/my-feature.md (basic template)

antemortem init my-migration --enhanced
# → Created antemortem/my-migration.md (enhanced template)
```

Copies the official Antemortem template with YAML frontmatter (`name`, `date`, `scope`, `reversibility`, `status: draft`). Output path: `./antemortem/<name>.md`.

### `antemortem run` — LLM-assisted classification

```bash
antemortem run antemortem/my-feature.md --repo ../target-repo
# Reading 6 files from ../target-repo ...
# Calling claude-opus-4-7 (cached system prompt, 4.2k input / 1.1k output) ...
# Classified 7 traps: 3 GHOST, 3 REAL, 1 NEW
# Citations written with file:line references.
# Updated: antemortem/my-feature.md
# Artifact: antemortem/my-feature.json
```

Reads the doc, extracts spec + traps + `files_to_read`, loads files from `--repo`, calls Claude Opus 4.7 with prompt caching on the frozen system prompt (~90% cost reduction on repeated runs), writes classifications back with `file:line` citations. Also emits a JSON artifact for `lint` and downstream tooling.

### `antemortem lint` — validate the schema and citations

```bash
antemortem lint antemortem/my-feature.md
# PASS — 7/7 traps classified, 7/7 citations present, 7/7 citations verify file:line.

antemortem lint antemortem/broken.md
# FAIL:
#   - trap#3: classification missing
#   - trap#5: citation format invalid ("see walk_forward.py" → expected "path:line")
#   - trap#6: cited file antemortem/ghost.py does not exist in --repo
# exit 1
```

Validates structured schema (all sections present, classifications complete) and verifies every `file:line` exists on disk. Exit 0 on pass, 1 on fail. Use in CI to block PRs with missing or fabricated citations.

## Model and cost

Uses Claude Opus 4.7 via the Anthropic SDK. Typical cost per `run`:

| Scenario | Cost |
|---|---|
| First run (writes system prompt to cache) | ~$0.18 |
| Cached run (system prompt + files reused within 5 min) | ~$0.11 |
| 100 iterations during development | $11–18 |

Cache miss indicators are surfaced in the CLI output so silent invalidators (e.g. non-deterministic prompt state) fail loud, not silent.

## Why a CLI (and not just "ask Claude to review my plan")

The discipline is two guardrails:

1. **Enumerate traps before the LLM sees them.** Prevents anchoring on the model's framing. The CLI surfaces this as a required section in the scaffolded document.
2. **Require `file:line` citations.** Prevents accepting the model's vibes. The CLI enforces this as a Pydantic schema field, and `lint` verifies the citations exist on disk (no hallucinated line numbers).

Without these guardrails, you have traded one form of hand-waving for another.

## Project status

v0.2.0 is the **initial release**. Alpha — API and output formats may change in v0.2.x as prompts iterate on real repos. Semver applies after v1.0.

Full changelog: [CHANGELOG.md](CHANGELOG.md).

## Relation to other projects

- [`Antemortem`](https://github.com/hibou04-ops/Antemortem) — the methodology, templates, and case studies. This CLI implements the `docs/methodology.md` protocol.
- [`omega-lock`](https://github.com/hibou04-ops/omega-lock) — first shipped case study of the discipline (audit submodule built with a 15-minute antemortem recon). Cited in Antemortem v0.1's case studies.

## License

MIT. See [LICENSE](LICENSE).

## Citing

```
Antemortem CLI v0.2 — tooling for the Antemortem pre-implementation reconnaissance discipline.
https://github.com/hibou04-ops/antemortem-cli, 2026.
```
