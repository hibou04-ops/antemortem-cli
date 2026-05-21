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

Rename invoice status values in the billing module before a broader refund-flow refactor.

## 2. Traps hypothesized (pre-recon)

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Renaming status values could miss the refund guard. | trap | 50% | refund path still compares string-backed status |
| 2 | Capture might ignore cancelled invoices. | worry | 20% | cancellation guard may be absent |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/billing.py`
- **Scope:** gallery fixture

## 4. Stored output

The expected output artifact is `recon.json`. It is a stored, offline fixture; no provider call is required.
