# Risky Refactor Preflight

Scenario: a planned workflow-status refactor could break rollback handling.

Reproduce offline:

```bash
antemortem lint examples/gallery/risky_refactor_preflight/recon.md --repo examples/gallery/risky_refactor_preflight/repo
```

Expected result: lint passes. The artifact classifies the rollback-status guard as `REAL`, the cancelled-execution concern as `GHOST`, and returns `PROCEED_WITH_GUARDS` because the real risk has a remediation.
