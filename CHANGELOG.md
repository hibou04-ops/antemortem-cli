# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/hibou04-ops/antemortem-cli/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/hibou04-ops/antemortem-cli/releases/tag/v0.3.0
[0.2.0]: https://github.com/hibou04-ops/antemortem-cli/releases/tag/v0.2.0
