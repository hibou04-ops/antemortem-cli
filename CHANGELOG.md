# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-04-21

Initial public release of the Antemortem CLI.

### Added

- `antemortem init <name>` — scaffold a new antemortem document from the basic template, or `--enhanced` for the enhanced template (calibration dimensions, fine-grained classification, skeptic pass, decision-first output).
- `antemortem run <doc>` — run LLM-assisted classification on an antemortem document using Claude Opus 4.7. Reads the spec, traps, and referenced files; returns REAL / GHOST / NEW labels with `file:line` citations; writes a JSON audit artifact.
- `antemortem lint <doc>` — validate an antemortem document's structured schema and verify all `file:line` citations exist in the current repository. Exit 0 on pass, 1 on fail. Suitable for CI.
- Embedded templates (basic + enhanced) vendored from [hibou04-ops/Antemortem](https://github.com/hibou04-ops/Antemortem) v0.1.1 under MIT.
- Pydantic v2 schemas for classifications, new traps, and spec mutations — shared end-to-end across `run` and `lint`.
- Prompt caching on the system prompt for Claude API calls, targeting the Opus 4.7 4096-token minimum to ensure cache hits.

### Scope boundary — not in v0.2

- Multi-model support (GPT, Gemini, etc.) — intentional, Claude Opus 4.7 only.
- GitHub Action / CI integration templates — follow in v0.3.
- HTML report rendering — follow in v0.3.
- Web dashboard / viewer — out of scope.
- Database-backed history — out of scope; files only.

### Rationale

Antemortem as a discipline was released as methodology-only in [Antemortem v0.1 / v0.1.1](https://github.com/hibou04-ops/Antemortem). The CLI operationalizes the protocol: scaffold, run, lint — three commands, one week to a disciplined antemortem doc. v0.2 ships the CLI; the methodology repo stays the source of truth for the protocol itself.

[Unreleased]: https://github.com/hibou04-ops/antemortem-cli/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/hibou04-ops/antemortem-cli/releases/tag/v0.2.0
