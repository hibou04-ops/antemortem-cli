---
name: binary-file-skipped
date: 2026-05-22
template: basic
---

# Antemortem - binary file skipped

## 1. The change

Inspect an asset loader without sending binary payloads to a provider.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | The binary asset may contain source-level behavior. | unknown | 40% | Binary safety |

## 3. Recon protocol

- **Files handed to the model:**
  - `assets/blob.bin`
