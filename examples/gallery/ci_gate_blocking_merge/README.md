# CI Gate Blocking Merge

Scenario: a deployment change would allow checks to be skipped.

Reproduce offline:

```bash
antemortem lint examples/gallery/ci_gate_blocking_merge/recon.md --repo examples/gallery/ci_gate_blocking_merge/repo
antemortem gate examples/gallery/ci_gate_blocking_merge/recon.md --repo examples/gallery/ci_gate_blocking_merge/repo
```

Expected result: lint passes, and `gate` exits nonzero because the stored decision is `DO_NOT_PROCEED`.
