---
name: fabricated-citation-rejected
date: 2026-05-21
template: basic
---

# Antemortem - fabricated citation rejected

## 1. The change

Require a feature flag before enabling a background job.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | The background job may run without the feature flag. | trap | 60% | Config guard |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/config.py`
