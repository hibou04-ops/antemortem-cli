---
name: ghost-exact-source-line
date: 2026-05-22
template: basic
---

# Antemortem - ghost exact source line

## 1. The change

Refactor cache loading without removing the existing cache hit path.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Cache loads may always bypass the in-memory cache. | trap | 65% | Cache |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/cache.py`
