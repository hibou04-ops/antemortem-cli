---
name: new-trap-valid-evidence-hash
date: 2026-05-22
template: basic
---

# Antemortem - new trap valid evidence hash

## 1. The change

Issue user sessions after login and audit the event.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Session issuance may skip audit logging. | trap | 50% | Audit |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/session.py`
