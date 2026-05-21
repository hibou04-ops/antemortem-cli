---
name: symlink-escape-citation
date: 2026-05-22
template: basic
---

# Antemortem - symlink escape citation

## 1. The change

Verify that citation resolution follows symlinks before accepting evidence.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | A symlink inside the repo may cite text outside the repo root. | trap | 80% | Path safety |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/link/escape.py`
