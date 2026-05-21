---
name: missing-file-unresolved
date: 2026-05-22
template: basic
---

# Antemortem - missing file unresolved

## 1. The change

Review a payment retry path whose implementation file was not supplied.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Payment retries may double-charge a user. | trap | 75% | Missing file |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/missing.py`
