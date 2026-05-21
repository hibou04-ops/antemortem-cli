---
name: gallery-ci-gate-blocking-merge
date: 2026-05-22
scope: change-local
reversibility: medium
status: classified
template: basic
---

# Antemortem — CI gate blocking merge

## 1. The change

Add a deployment option that can bypass checks for emergency changes.

## 2. Traps hypothesized (pre-recon)

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | The merge gate should block any skip-checks deployment path. | trap | 80% | CI policy boundary |
| 2 | Region validation may be missing. | worry | 25% | deploy config |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/deploy.py`
- **Scope:** gallery fixture

## 4. Stored output

The expected output artifact is `recon.json`. It is a stored, offline fixture; no provider call is required.
