---
name: gallery-security-sensitive-change
date: 2026-05-22
scope: change-local
reversibility: low
status: classified
template: basic
---

# Antemortem — security-sensitive change

## 1. The change

Allow API-key rotation from the account settings flow.

## 2. Traps hypothesized (pre-recon)

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Owners may rotate keys without reauthentication. | trap | 70% | auth boundary |
| 2 | Audit records may omit the actor id. | worry | 25% | forensic record |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/authz.py`
- **Scope:** gallery fixture

## 4. Stored output

The expected output artifact is `recon.json`. It is a stored, offline fixture; no provider call is required.
