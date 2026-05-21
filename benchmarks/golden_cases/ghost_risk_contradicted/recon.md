---
name: ghost-risk-contradicted
date: 2026-05-21
template: basic
---

# Antemortem - ghost risk contradicted by code

## 1. The change

Reuse the cache header helper in a new endpoint.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Cache responses may never expire. | trap | 50% | Header behavior |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/cache.py`
