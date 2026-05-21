---
name: wrong-evidence-snippet
date: 2026-05-22
template: basic
---

# Antemortem - wrong evidence snippet

## 1. The change

Wire the delete authorization helper into the new administration route.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Non-admin users may pass the delete authorization check. | trap | 70% | Auth boundary |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/authz.py`
