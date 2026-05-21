---
name: citation-range-too-large
date: 2026-05-22
template: basic
---

# Antemortem - citation range too large

## 1. The change

Refactor route registration while preserving the existing route table.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | The refactor may drop registered routes. | trap | 60% | Route table |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/routes.py`
