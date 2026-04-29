# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2026-04-29

### Added

- **MCP server** (`antemortem.mcp`) — FastMCP-based server that exposes the three CLI commands (`scaffold`, `run`, `lint`) as agent-callable MCP tools. Run with `python -m antemortem.mcp` (stdio transport, default for Claude Code / Cursor) or `--http` (streamable-http transport). Console script `antemortem-mcp` registered.
- **New optional dependency `[mcp]`** — `pip install "antemortem[mcp]"` pulls in the official MCP Python SDK (`mcp>=1.0.0`).
- **6 new smoke tests** verifying all three tools register with descriptions, input schemas, and required-args contracts that match the underlying CLI.

### Rationale

0.5.0 made antemortem available as a CLI and as a Python import. 0.6.0 makes it available as an *MCP tool surface*, so agents (Claude Code, Cursor, custom runtimes) can call `scaffold` / `run` / `lint` as tools the same way a human invokes the CLI. The discipline (file:line citations, REAL/GHOST/NEW/UNRESOLVED classification, four-level decision gate) is unchanged; the MCP layer is a thin agent-facing wrapper around the same primitives the CLI uses.

The intended agent flow before any non-trivial code edit: `scaffold` → fill in spec / traps / files_to_read → `run` (LLM classifies risks against actual repo files) → `lint` (verify citations are not hallucinated) → proceed only if the decision gate clears.

## [0.5.0] - 2026-04-28

### Changed

- **License: MIT → Apache 2.0 (PyPI distribution alignment).** 0.2.0, 0.3.0, and 0.4.0 were published with an MIT `LICENSE` file because the relicense to Apache 2.0 happened on 2026-04-22 (commit `f49af09`) after the 0.4.0 PyPI upload. 0.5.0 publishes with the Apache 2.0 LICENSE in the package, matching the classifier `License :: OSI Approved :: Apache Software License` already declared in `pyproject.toml`. PyPI distributions of 0.4.0 and earlier remain under the MIT license they shipped with — license changes do not apply retroactively. See README License section for full history.

### Rationale

Bumped to a minor (0.5.0) rather than a patch (0.4.1) because a license change — even one that was already reflected in the repository LICENSE file — is a policy change for downstream users, not a bugfix. Treating it as a minor signals to dependency-pinning consumers that they should re-review terms before upgrading.

## [0.4.0] - 2026-04-22

### Added

- **Critic pass (2-pass adversarial review)** — opt-in via `--critic` flag on `antemortem run`. A second provider call reviews every REAL and NEW finding from the first pass and returns `CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE`. Policy automatically downgrades weakened findings to UNRESOLVED and drops duplicates before the decision gate runs. Roughly doubles per-run API cost; ships off by default.
- **`CriticResult` schema** (`antemortem.schema.CriticResult`) — records `finding_id`, `status`, `issues`, `counterevidence` citations, and an optional `recommended_label`. Attached to the artifact's new `critic_results` array for audit-trail completeness.
- **`critic.py` module** — `run_critic_pass` delegates to the configured `LLMProvider` with a dedicated ~1.5k-token `CRITIC_SYSTEM_PROMPT`; `apply_critic_results` applies the downgrade policy deterministically.
- **Four-level decision gate** (`antemortem.decision.compute_decision`) — maps the final artifact to one of `SAFE_TO_PROCEED` / `PROCEED_WITH_GUARDS` / `NEEDS_MORE_EVIDENCE` / `DO_NOT_PROCEED` based on finding counts, severity, remediation presence, and critic outcomes. CLI colour-codes the decision and prints a one-sentence rationale. `--no-decision` skips the gate for callers that want the raw artifact only.
- **Optional per-finding fields**: `Classification` and `NewTrap` gain `confidence` (0.0–1.0), `remediation` (concrete mitigation suggestion), and `severity` (`low` / `medium` / `high`). All optional — v0.3.x artifacts remain valid. The decision gate consults `severity` and `remediation` to gate DO_NOT_PROCEED on unmitigated high-severity REAL findings.
- **25 new tests** — `test_critic.py` covers each critic status policy, `test_decision.py` covers all four decision outcomes. Total **111 tests passing**, still zero network calls in CI.

### Changed

- **`AntemortemOutput` schema gains three optional fields**: `critic_results`, `decision`, `decision_rationale`. All default to empty/null so v0.3.x callers and v0.3.x artifacts still validate.
- **CLI output on `run`** now appends a colour-coded decision line when the gate fires, and a short rationale on the next line. JSON summary (`ANTEMORTEM_JSON_SUMMARY=1`) exposes `decision` and `critic_ran` alongside the existing fields.

### Rationale

v0.3.0 shipped multi-provider infrastructure but kept the output surface as a raw first-pass classification. The advisor pattern (`recongate` reference architecture) called out two complementary additions as the highest-leverage next steps: a 2-pass critic (quality layer) and a 4-level decision gate (CI integration depth). v0.4 implements both, with defaults that keep the existing behaviour intact for users who don't opt in.

Critic rationale: the classifier's REAL label is the noisiest end of the pipeline. A dedicated adversarial-review pass that *only* downgrades (never upgrades) is a strict quality multiplier at the cost of one extra API call. The prompt is explicit about this asymmetry so the critic doesn't drift into re-classification territory.

Decision gate rationale: a single pass/fail signal was too coarse to drive CI decisions. The four-level enum maps cleanly onto common CI patterns (auto-merge / require-approval / block / investigate) without baking in any specific organisation's policy — teams override by whitelisting or blacklisting specific decision levels.

### Migration from v0.3.x

No breaking changes. Existing commands and artifacts work unchanged. To adopt the new features:

- Add `--critic` to `antemortem run` for the second-pass review. Doubles API cost per invocation; use during high-stakes recons.
- Artifact now includes `decision` and `decision_rationale` by default. If your CI pipeline reads the JSON, you can ignore the new fields or gate on them. Pass `--no-decision` to suppress.

## [0.3.0] - 2026-04-22

### Added

- **`LLMProvider` Protocol + `providers/` package** — the CLI is now model-agnostic. The discipline (schema enforcement, file:line citations, disk-verified lint) is vendor-neutral; only the single API-call boundary is pluggable. Each adapter uses its vendor's strongest native schema-enforcement mechanism (no client-side JSON regex fallback anywhere).
- **Anthropic adapter** (`antemortem/providers/anthropic_provider.py`) — uses `messages.parse(output_format=AntemortemOutput)`, explicit `cache_control={"type": "ephemeral"}`, adaptive thinking + `effort` configurable.
- **OpenAI adapter** (`antemortem/providers/openai_provider.py`) — uses `beta.chat.completions.parse(response_format=AntemortemOutput)`. Accepts custom `base_url`, so any OpenAI-compatible endpoint works as a drop-in: Azure OpenAI, Groq, Together.ai, OpenRouter, local Ollama at `http://localhost:11434/v1`.
- **`make_provider(name, model, api_key, base_url)`** factory and `supported_providers()` helper for discovering what this build supports.
- **CLI flags on `antemortem run`**: `--provider {anthropic,openai}`, `--model <str>`, `--base-url <url>`. Each provider has a sensible default model; override only when you need to.
- **18 new tests** covering the factory, both adapters, and cross-SDK usage-normalization (`prompt_tokens_details.cached_tokens` → `cache_read_input_tokens`). Total test count: 86, still zero network calls in CI.

### Changed

- **Dependencies** now include both `anthropic>=0.40.0` and `openai>=1.50.0` by default. The `pip install antemortem` install-happy path gives users both providers out of the box. Slim installs via `pip install antemortem[anthropic]` or `pip install antemortem[openai]` still work for users who want to strip one.
- **`api.py` no longer imports the Anthropic SDK directly.** The call site uses the `LLMProvider` abstraction, so swapping providers is one flag, not a code change.
- **CLI output** now surfaces the configured provider and model on every run: `Calling anthropic model claude-opus-4-7 ...` instead of a hardcoded string. This makes reproducibility a user-visible property of each run.
- **Exit code 2** continues to be used for environment issues, including now "unknown `--provider`" and per-provider missing API key (`ANTHROPIC_API_KEY` for `anthropic`, `OPENAI_API_KEY` for `openai`).

### Rationale

v0.2.0 hard-pinned a single Claude model. That was correct for a fresh prompt contract but the wrong framing for a general-purpose discipline tool. The antemortem pattern — enumerate first, cite file:line, lint verifies on disk — is not vendor-specific, and the tool shouldn't pretend to be either. The provider abstraction keeps v0.2's rigor (Pydantic enforcement at the SDK boundary, schema validation per call, disk-verified citations) while unlocking the full frontier-LLM ecosystem including local models via Ollama.

### Migration from v0.2.x

`antemortem run` continues to default to the Anthropic provider, so existing users with `ANTHROPIC_API_KEY` set see no behavior change. Users who want OpenAI or a compatible endpoint add `--provider openai` (and optionally `--model gpt-4o` or `--base-url http://localhost:11434/v1`). The JSON artifact schema (`AntemortemOutput`) is unchanged, so existing `<doc>.json` files still lint correctly.

## [0.2.0] - 2026-04-22

Initial public release of the Antemortem CLI.

### Added

- `antemortem init <name>` — scaffold a new antemortem document from the basic template, or `--enhanced` for the enhanced template (calibration dimensions, fine-grained classification, skeptic pass, decision-first output).
- `antemortem run <doc>` — run LLM-assisted classification on an antemortem document using Claude Opus 4.7. Reads the spec, traps, and referenced files; returns REAL / GHOST / NEW labels with `file:line` citations; writes a JSON audit artifact.
- `antemortem lint <doc>` — validate an antemortem document's structured schema and verify all `file:line` citations exist in the current repository. Exit 0 on pass, 1 on fail. Suitable for CI.
- Embedded templates (basic + enhanced) vendored from [hibou04-ops/Antemortem](https://github.com/hibou04-ops/Antemortem) v0.1.1 under MIT.
- Pydantic v2 schemas for classifications, new traps, and spec mutations — shared end-to-end across `run` and `lint`.
- Prompt caching on the system prompt for Claude API calls, targeting the Opus 4.7 4096-token minimum to ensure cache hits.

### Scope boundary — not in v0.2

- Multi-model support (GPT, Gemini, etc.) — **added in v0.3.**
- GitHub Action / CI integration templates — follow in v0.4+.
- HTML report rendering — follow in v0.4+.

### Rationale

Antemortem as a discipline was released as methodology-only in [Antemortem v0.1 / v0.1.1](https://github.com/hibou04-ops/Antemortem). The CLI operationalizes the protocol: scaffold, run, lint — three commands, one week to a disciplined antemortem doc. v0.2 ships the CLI; the methodology repo stays the source of truth for the protocol itself.

[Unreleased]: https://github.com/hibou04-ops/antemortem-cli/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/hibou04-ops/antemortem-cli/releases/tag/v0.4.0
[0.3.0]: https://github.com/hibou04-ops/antemortem-cli/releases/tag/v0.3.0
[0.2.0]: https://github.com/hibou04-ops/antemortem-cli/releases/tag/v0.2.0
