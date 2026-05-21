# Risky Refactor Preflight

Scenario: a planned billing-status refactor could break refund handling.

Reproduce offline:

```bash
antemortem lint examples/gallery/risky_refactor_preflight/recon.md --repo examples/gallery/risky_refactor_preflight/repo
```

Expected result: lint passes. The artifact classifies the refund-status guard as `REAL`, the cancelled-capture concern as `GHOST`, and returns `PROCEED_WITH_GUARDS` because the real risk has a remediation.
