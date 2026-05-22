# CLI Example Gallery

These examples are offline fixtures. Each case includes:

- `recon.md`
- `repo/` fixture files
- `recon.json` expected output artifact
- `README.md` with the reproduction command

Run every example with:

```bash
python -m pytest tests/test_examples_gallery.py -q
```

## Cases

| Case | Scenario | Offline command |
|---|---|---|
| `risky_refactor_preflight` | Billing-status refactor preflight with one real risk and one ghost risk. | `antemortem lint examples/gallery/risky_refactor_preflight/recon.md --repo examples/gallery/risky_refactor_preflight/repo` |
| `agent_generated_patch_review` | Agent-generated profile patch review with allowlist evidence. | `antemortem lint examples/gallery/agent_generated_patch_review/recon.md --repo examples/gallery/agent_generated_patch_review/repo` |
| `security_sensitive_change` | API-key rotation change where a high-severity authorization risk blocks progress. | `antemortem lint examples/gallery/security_sensitive_change/recon.md --repo examples/gallery/security_sensitive_change/repo` |
| `missing_evidence_unresolved` | Missing worker evidence produces `NEEDS_MORE_EVIDENCE`. | `antemortem lint examples/gallery/missing_evidence_unresolved/recon.md --repo examples/gallery/missing_evidence_unresolved/repo` |
| `ci_gate_blocking_merge` | Lint passes, then `gate` blocks a `DO_NOT_PROCEED` artifact. | `antemortem gate examples/gallery/ci_gate_blocking_merge/recon.md --repo examples/gallery/ci_gate_blocking_merge/repo` |

The gallery does not call providers. The JSON artifacts are stored fixtures and are validated by `lint` against their fixture repos.

---

This page is part of the [`antemortem-cli`](../README.md) documentation set.
