---
name: demo-recon
date: 2026-04-27
scope: change-local
reversibility: high
status: classified
template: basic
---

# Antemortem — paced demo command

**Date:** 2026-04-27
**Author:** Hibou
**Repo:** `antemortem-cli`
**Model used for recon:** Claude Opus 4.7

---

## 1. The change

Add a paced walk-through demo that runs a real antemortem document end-to-end
(traps → classifications → decision → lint), with deliberate pauses so a
60-second screencast can capture each phase. The demo reuses the existing
`lint` command for citation verification — no new provider plumbing.

## 2. Traps hypothesized (pre-recon)

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | Demo couples to a specific provider — non-deterministic output | trap | 60% | provider config in lint? |
| 2 | Citation regex would reject Windows paths with backslashes | worry | 30% | win32 might break |
| 3 | Decision enum string drifts between rule code and schema | trap | 25% | hardcoded vs Literal? |
| 4 | Lint reads files synchronously; large repos slow demo | unknown | 20% | path resolution overhead |

## 3. Recon protocol

- **Files handed to the model:**
  - `src/antemortem/cli.py`
  - `src/antemortem/citations.py`
  - `src/antemortem/decision.py`
  - `src/antemortem/schema.py`
- **Time spent:** ~10 min
- **Scope:** narrow

## 4. Findings (classification with citations)

### Trap #1 → GHOST

- **Evidence:** `src/antemortem/cli.py:1-44` — the CLI is a thin Typer app whose
  `lint` subcommand takes no provider option. No shared provider state across
  subcommands.
- **Classification rationale:** Decoupled by design; the demo flow (which calls
  only `lint`) does not need an LLM provider. The original worry was based on
  a wrong mental model.
- **Revised P(issue):** 0%.

### Trap #2 → REAL

- **Evidence:** `src/antemortem/citations.py:15-25` — `_CITATION_RE` matches any
  non-whitespace, non-colon path. Backslashes pass the regex; the platform-
  specific work happens in `verify_citation`.
- **Classification rationale:** The regex itself is fine, but the reverse case
  bites: a path written with `/` on a doc authored on Linux still resolves on
  Windows because `pathlib.Path` normalizes both separators. The remediation is
  documentation, not code: tell authors to use forward slashes.
- **Revised P(issue):** 10% (down from 30%).

### Trap #3 → GHOST

- **Evidence:** `src/antemortem/decision.py:30-35` defines `DECISION_LABELS` as
  the canonical tuple of four strings, and the rule logic compares against
  literals from this same module.
- **Classification rationale:** Single source of truth; no drift possible.
- **Revised P(issue):** 0%.

### Trap #4 → UNRESOLVED

- **Evidence:** none in the files handed to the model. No benchmark exists for
  citation verification on repos with >1000 citations, and the recon scope did
  not include profiling work.
- **Classification rationale:** Genuinely unresolved — needs a measurement pass
  before claiming GHOST or REAL. Not blocking for the small demo doc.
- **Revised P(issue):** 20% (unchanged).

### New finding surfaced by the recon → t_new_1 (NEW)

- **Evidence:** `src/antemortem/schema.py:177-222` — `AntemortemOutput.decision`
  is optional (`| None`). A model that omits it should not silently produce a
  `SAFE_TO_PROCEED` verdict; the CLI must explicitly compute the decision after
  classification.
- **Classification rationale:** Was not on the original traps list, but worth
  guarding before the demo claims any specific decision.
- **Severity:** medium — affects correctness of demo output.

## 5. Probability revision

- **Pre-recon overall P(success):** 60%
- **Post-recon overall P(success):** 92%
- **What the recon bought:** 2 traps fully eliminated (GHOST), 1 confirmed REAL
  with concrete documentation remediation, 1 deferred as UNRESOLVED with
  explicit scope (large-repo perf).

## 6. Spec changes triggered

- Add a "use forward slashes in citation paths" note to the antemortem template
- Document citation-count perf in README under "When NOT to use"

## 7. Implementation checklist (post-recon)

- [x] Write a real demo antemortem doc (this file)
- [x] Wire `lint` to verify citations against disk
- [ ] Capture demo output → `_demo_output.txt`
- [ ] Tune `demo_replay.py` SECTION_PAUSES to match the SRT cues

---

*Demo fixture for `examples/demo_replay.py`. Used by the README's 60-second
screencast.*
