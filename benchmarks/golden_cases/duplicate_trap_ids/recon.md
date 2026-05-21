---
name: duplicate-trap-ids
date: 2026-05-22
template: basic
---

# Antemortem - duplicate trap ids

## 1. The change

Update feature flag handling before removing an old rollout path.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | The feature may already be enabled by default. | trap | 60% | Flag state |
| 1 | The disabled path may still be reachable. | worry | 40% | Duplicate id |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/flags.py`
