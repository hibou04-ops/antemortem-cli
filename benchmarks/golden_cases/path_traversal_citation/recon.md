---
name: path-traversal-citation
date: 2026-05-22
template: basic
---

# Antemortem - path traversal citation

## 1. The change

Review a loader that should only read files inside the repository root.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | The loader may trust paths outside the repo. | trap | 75% | Path safety |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/app.py`
