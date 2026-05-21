---
name: gallery-agent-generated-patch-review
date: 2026-05-22
scope: change-local
reversibility: high
status: classified
template: basic
---

# Antemortem — agent-generated patch review

## 1. The change

Review an agent-generated profile update helper before accepting the patch into the main branch.

## 2. Traps hypothesized (pre-recon)

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | The patch may allow arbitrary role changes. | trap | 60% | agent code often overgeneralizes setters |
| 2 | Missing patch payload may be accepted silently. | worry | 35% | parser default could hide caller bugs |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/profile_update.py`
- **Scope:** gallery fixture

## 4. Stored output

The expected output artifact is `recon.json`. It is a stored, offline fixture; no provider call is required.
