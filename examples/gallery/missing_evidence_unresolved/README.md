# Missing Evidence Causing Unresolved Decision

Scenario: the plan asks about retry behavior, but the provided file does not include the worker implementation.

Reproduce offline:

```bash
antemortem lint examples/gallery/missing_evidence_unresolved/recon.md --repo examples/gallery/missing_evidence_unresolved/repo
```

Expected result: lint passes. The artifact returns `NEEDS_MORE_EVIDENCE` because the trap is `UNRESOLVED` with `citation=null`.
