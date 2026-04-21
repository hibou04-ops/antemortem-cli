"""Embedded Antemortem document templates.

Vendored from hibou04-ops/Antemortem v0.1.1 (MIT). The basic template matches
``templates/antemortem-template.md`` and the enhanced template matches
``templates/antemortem-template-enhanced.md`` in that repository at the tagged
``v0.1.1`` commit.

Keep these strings in sync with the upstream templates on Antemortem version
bumps — see CHANGELOG.md for the version of upstream we currently ship.
"""

UPSTREAM_VERSION = "0.1.1"


BASIC_TEMPLATE = r"""# Antemortem — <change name>

**Date:** YYYY-MM-DD
**Author:** <you>
**Repo / branch:** <where this change will live>
**Model used for recon:** <e.g., Claude Opus 4.7>

---

## 1. The change

<One paragraph. What are you planning to add, remove, or refactor? What problem does it solve? What is the user-visible effect? Be concrete.>

## 2. Traps hypothesized (pre-recon)

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | <description> | trap / worry / unknown | % | <why you suspect this> |
| 2 | | | | |
| 3 | | | | |

> Label guide: **trap** = I think this is real. **worry** = I'm unsure. **unknown** = I haven't thought about this region yet.

## 3. Recon protocol

- **Files handed to the model:**
  - `<path/to/file1>`
  - `<path/to/file2>`
  - `<path/to/file3>`
- **Time spent:** <minutes>
- **Scope:** <narrow / normal / wide — how much of the code the model read>

## 4. Findings (classification with citations)

For each trap in the table above, classify REAL / GHOST / NEW and cite file + line.

### Trap #1 → <REAL | GHOST | NEW>

- **Evidence:** `<file>:<line>` — <what the code shows>
- **Classification rationale:** <why the evidence supports this label>
- **Revised P(issue):** <%>

### Trap #2 → <REAL | GHOST | NEW>

- **Evidence:** `<file>:<line>`
- **Classification rationale:**
- **Revised P(issue):**

### New findings surfaced by the recon

- <anything the model pointed out that was not on the original traps list>

## 5. Probability revision

- **Pre-recon overall P(success):** <%>
- **Post-recon overall P(success):** <%>
- **What the recon bought:** <sentence summarizing where the probability moved and why>

## 6. Spec changes triggered

- <concrete edit 1 to the spec, with rationale>
- <concrete edit 2>
- <concrete edit 3>

## 7. Implementation checklist (post-recon)

- [ ] <step 1>
- [ ] <step 2>
- [ ] <step 3>

## 8. Post-implementation note (optional — fill in later)

Once implementation is done, add a short paragraph:

- Did the traps you kept on the list actually bite? Which ones?
- Did anything break that the antemortem missed?
- What would you change in the recon protocol for next time?

---

*Template version 0.1 (upstream Antemortem v0.1.1). Based on the methodology at [github.com/hibou04-ops/Antemortem](https://github.com/hibou04-ops/Antemortem).*
"""


ENHANCED_TEMPLATE = r"""# Antemortem (enhanced) — <change name>

**Date:** YYYY-MM-DD
**Author:** <you>
**Repo / branch:** <where this change will live>
**Model used for recon:** <e.g., Claude Opus 4.7>
**Template:** enhanced (incorporates calibration dimensions + skeptic loop + decision-first output)

> This is the **enhanced** template, a superset of `antemortem-template.md`. Use when the change is high-stakes, touches prod data, is hard to reverse, or when you want stronger false-positive control. Solo-use optimized.
>
> **Philosophy:** every trap gets weighed on four axes (P, evidence, blast, reversibility), classified with a fine-grained subtype, and explicitly challenged by a skeptic pass. The output is not a risk list — it is five blocks of decisions you can act on during implementation.
>
> **Reading guide for future-you:** if you come back to this doc after the implementation surprises you, read sections 6 (Decision document) and 8 (Post-implementation note) first. They are where the recon's conclusions and reality's verdict meet.

---

## 1. The change

<One paragraph. What are you planning to add, remove, or refactor? What problem does it solve? What is the user-visible effect? Be concrete.>

### 1.1 Assumed invariants (explicit)

<What the existing system guarantees that this change should preserve. List 2-5.>
- Invariant 1:
- Invariant 2:

### 1.2 Unknowns declared up front

<What you are NOT confident about — even before recon.>
- Unknown 1:
- Unknown 2:

---

## 2. Traps hypothesized (pre-recon) — calibrated

Extended table with calibration dimensions. Each trap gets scored on four axes before recon, updated after.

| # | trap | type | P(issue) | evidence strength | blast radius | reversibility | notes |
|---|------|------|----------|-------------------|--------------|---------------|-------|
| 1 | <description> | trap/worry/unknown | %  | low/mid/high | local/module/service/system | easy/hard/irrecoverable | <why you suspect this> |
| 2 | | | | | | | |

**Type key:**
- **trap** — you believe this is real
- **worry** — unsure
- **unknown** — you haven't thought about this region yet

**Evidence strength** (gut pre-recon):
- low = "just a feeling"
- mid = "I've seen this pattern before"
- high = "the docs/code structure hints at this"

**Blast radius**:
- local = single function/class
- module = single module/file
- service = one service
- system = cross-service or data

**Reversibility**:
- easy = fix forward in same PR
- hard = needs migration / coordinated rollback
- irrecoverable = data loss / external commitment

---

## 3. Recon protocol

- **Files handed to the model:**
  - `<path/to/file1>`
  - `<path/to/file2>`
  - `<path/to/file3>`
- **Time budget:** <minutes>
- **Scope:** narrow / normal / wide
- **Recon mode:** Judge-only / Judge + Skeptic (recommended for high-stakes)

---

## 4. Findings (classification with citations)

Each trap gets **fine-grained classification** (not just REAL/GHOST/NEW):

**REAL subtypes:**
- `REAL-structural` — code confirms the risk (static evidence)
- `REAL-runtime-uncertain` — code suggests; only runtime can confirm

**GHOST subtypes:**
- `GHOST-mitigated` — exists but already handled upstream
- `GHOST-unreachable` — code path doesn't actually trigger
- `GHOST-assumption-error` — hypothesis was based on wrong mental model
- `GHOST-test-covered` — test explicitly fixes invariant

**NEW subtypes (surfaced during recon):**
- `NEW-spec-gap` — missing requirement not covered by spec
- `NEW-coupling` — hidden dependency between modules
- `NEW-operational` — runtime/ops concern (observability, rollout)
- `NEW-policy` — policy/permission/compliance angle

### Trap #1 → <classification>

- **Evidence:** `<file>:<line>` — <what the code shows, quoted if short>
- **Classification rationale:** <why the evidence supports this label>
- **Revised P(issue):** <%>
- **Revised calibration:** evidence=<low/mid/high>, blast=<...>, reversibility=<...>
- **Confidence in this classification:** <0.0-1.0> — <why this confidence level>

### Trap #2 → ...

### New findings (surfaced by the recon)

- <anything the model pointed out that was not on the original traps list — classify same as above>

---

## 4b. Skeptic pass (for REAL and NEW classifications)

> **Purpose: kill the false positives before they make it to the spec.**
>
> For each finding classified as REAL or NEW in step 4, explicitly challenge it. Search for counterevidence. If you cannot find counterevidence after looking, the classification stands with higher confidence.

### Trap #1 (REAL-structural) — skeptic challenge

- **Counter-hypothesis considered:** <pick one or more from the patterns below>
- **Search for counterevidence:** <what I looked for, in which files>
- **Result:** confirmed REAL / **downgraded to GHOST-<subtype>** / uncertain
- **Final classification:** <keep or update>

### Trap #2 — skeptic challenge
...

**Counter-hypothesis patterns to try:**
- A mitigation might already exist in the call site, caller, or config.
- The code path might not actually trigger under the conditions this change introduces.
- A test might already pin the invariant.
- The hypothesis might be based on a wrong mental model of the module.
- The model may have pattern-matched a shape (e.g., "this looks recursive") that the specific code doesn't instantiate.

**Skeptic's mantra:**
> *"The code shows X"* is not evidence. *"Line 82 of `walk_forward.py` calls `evaluate()` once per params, with no surrounding loop"* is.

---

## 5. Probability revision

- **Pre-recon overall P(success):** <%>
- **Post-recon overall P(success):** <%>
- **Confidence in this overall estimate:** <0.0-1.0>
- **What the recon bought:**
  - ghost count: <before -> after>
  - risk downgrades: <count + brief>
  - new findings: <count + brief>
  - time saved (est.): <engineer-hours>

---

## 6. Decision document (enhanced output)

> Structure the output around **decisions to make**, not risks to worry about. Five blocks.

### A. Decision blockers

<Items that must be resolved BEFORE implementation starts. Max 3.>

- [ ] Blocker 1:
- [ ] Blocker 2:

### B. Spec mutations required

<Specific, concrete changes to the spec / requirements document before coding.>

- Mutation 1: <what changes, why>
- Mutation 2:

### C. Safe implementation path

<Ordered steps to implement this change with lowest risk.>

1. Step 1:
2. Step 2:
3. Step 3:

### D. Runtime validation needed

<Things static recon cannot answer. Require empirical verification during/after implementation.>

- [ ] Validation 1: <what to measure, when, threshold>
- [ ] Validation 2:

### E. Deprioritized risks

<Risks consciously deferred, with reason. Prevents noise while preserving honesty.>

| risk | why deprioritized |
|------|-------------------|
| <...> | <e.g., "low blast radius + rollback easy"> |

---

## 7. Implementation checklist (post-decision)

- [ ] All Decision blockers (section 6A) resolved
- [ ] All Spec mutations (section 6B) applied
- [ ] Implementation follows Safe path (section 6C)
- [ ] Runtime validation plan in place (section 6D)
- [ ] <step 1 concrete>
- [ ] <step 2 concrete>

---

## 8. Post-implementation note

Once implementation is done, add a paragraph + update the **Prediction feedback** table.

**Prose:**
- Which REAL/NEW findings bit as expected?
- What broke that the antemortem missed?
- Which Skeptic challenges were right to downgrade?
- What would change in the protocol for next time?

**Prediction feedback:**

| finding | predicted | confirmed in reality? | notes |
|---------|-----------|----------------------|-------|
| Trap #1 | REAL-structural | yes/no/partial | |
| Trap #2 | GHOST-mitigated (skeptic downgrade) | skeptic correct? | |
| New #1 | NEW-spec-gap | accepted into spec? | |

> **Feedback discipline: over time, your own prediction-to-reality ratio becomes the strongest signal of when to trust (or distrust) the antemortem. This table is where that signal accumulates.**

---

## Usage notes for this enhanced template

**When to use this over the basic template:**
- High-stakes change (prod deploy, data migration, security boundary)
- You want the Skeptic pass to kill false positives
- You're accumulating a personal track record and want the prediction-feedback loop

**When the basic template is enough:**
- Small change, low blast radius
- Exploration / prototype work
- 5-minute recon

**Version:** enhanced v0.1 (upstream Antemortem v0.1.1). Incorporates calibration dimensions, fine-grained classification, explicit skeptic pass, and decision-first output from v2+ architecture notes. Compatible with `docs/methodology.md` seven-step protocol — the protocol is unchanged; the doc structure just gets richer.

---

*Based on the methodology at [github.com/hibou04-ops/Antemortem](https://github.com/hibou04-ops/Antemortem).*
"""


def get_template(enhanced: bool = False) -> str:
    """Return the basic or enhanced template text."""
    return ENHANCED_TEMPLATE if enhanced else BASIC_TEMPLATE
