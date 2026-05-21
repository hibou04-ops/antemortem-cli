---
name: real-risk-valid-citation
date: 2026-05-21
template: basic
---

# Antemortem - real risk with valid citation

## 1. The change

Tighten the admin authorization helper before wiring it into a new route.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Anonymous users may be treated as administrators. | trap | 70% | Auth boundary |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/auth.py`
