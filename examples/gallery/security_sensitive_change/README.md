# Security-Sensitive Change

Scenario: an API-key rotation change touches authorization behavior.

Reproduce offline:

```bash
antemortem lint examples/gallery/security_sensitive_change/recon.md --repo examples/gallery/security_sensitive_change/repo
```

Expected result: lint passes. The artifact returns `DO_NOT_PROCEED` because a high-severity owner-rotation path is real and not remediated in the proposed plan.
