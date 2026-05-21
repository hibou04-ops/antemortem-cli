---
name: demo-recon
date: 2026-04-27
scope: change-local
reversibility: high
status: draft
template: basic
---

# Antemortem - demo recon

## 1. The change

Run the bundled deterministic demo flow and verify that the CLI can parse the
recon document, inspect source files, and report readiness before any provider
call is made.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Demo command accidentally depends on a live provider | trap | 40% | should be local |
| 2 | Citation parsing rejects Windows-style paths | worry | 30% | path normalization |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/antemortem/cli.py`
  - `src/antemortem/citations.py`
