---
name: gallery-risky-refactor-preflight
date: 2026-05-22
scope: change-local
reversibility: medium
status: classified
template: basic
---

# Antemortem — risky refactor preflight

## 1. The change

Rename task status values in the workflow module before a broader rollback-flow refactor.

## 2. Traps hypothesized (pre-recon)

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Renaming status values could miss the rollback guard. | trap | 50% | rollback path still compares string-backed status |
| 2 | Execution might ignore cancelled tasks. | worry | 20% | cancellation guard may be absent |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/workflow.py`
- **Scope:** gallery fixture

## 4. Stored output

The expected output artifact is `recon.json`. It is a stored, offline fixture; no provider call is required.
