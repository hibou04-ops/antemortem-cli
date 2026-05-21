---
name: malformed-schema-rejected
date: 2026-05-21
template: basic
---

# Antemortem - malformed schema rejected

## 1. The change

Add a delete endpoint.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Delete endpoint may lack authorization. | trap | 80% | Auth boundary |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/delete.py`
