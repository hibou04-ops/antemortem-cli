---
name: high-severity-real-blocks
date: 2026-05-22
template: basic
---

# Antemortem - high severity real blocks

## 1. The change

Expose the account deletion helper to an administrative route.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Account deletion may run without an audit record. | trap | 80% | Audit blocker |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/admin.py`
