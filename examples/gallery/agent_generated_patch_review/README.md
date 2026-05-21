# Agent-Generated Patch Review

Scenario: an agent proposes profile-update code. The stored artifact separates a ghost risk from a real parsing risk.

Reproduce offline:

```bash
antemortem lint examples/gallery/agent_generated_patch_review/recon.md --repo examples/gallery/agent_generated_patch_review/repo
```

Expected result: lint passes. The artifact records that arbitrary field mutation is contradicted by the allowlist, while missing-patch parsing remains `REAL` with a remediation.
