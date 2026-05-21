---
name: new-trap-surfaced
date: 2026-05-21
template: basic
---

# Antemortem - new trap surfaced

## 1. The change

Reuse the upload helper for externally supplied files.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Oversized uploads may be accepted. | trap | 60% | Size guard |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/upload.py`
