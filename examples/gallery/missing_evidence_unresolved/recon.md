---
name: gallery-missing-evidence-unresolved
date: 2026-05-22
scope: change-local
reversibility: high
status: classified
template: basic
---

# Antemortem — missing evidence unresolved

## 1. The change

Change queue enqueueing before reviewing the worker retry path.

## 2. Traps hypothesized (pre-recon)

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Worker retries may double-charge customers. | unknown | 50% | worker file not included |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/workflow.py`
- **Scope:** gallery fixture

## 4. Stored output

The expected output artifact is `recon.json`. It is a stored, offline fixture; no provider call is required.
