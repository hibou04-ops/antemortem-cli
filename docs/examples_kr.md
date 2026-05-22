# CLI Example Gallery

이 예시는 모두 offline fixture입니다. 각 case는 다음 파일을 포함합니다.

- `recon.md`
- `repo/` fixture files
- `recon.json` expected output artifact
- 재현 명령이 적힌 `README.md`

전체 예시는 다음 명령으로 검증합니다.

```bash
python -m pytest tests/test_examples_gallery.py -q
```

## Cases

| Case | Scenario | Offline command |
|---|---|---|
| `risky_refactor_preflight` | Billing status refactor 전에 real risk와 ghost risk를 분리합니다. | `antemortem lint examples/gallery/risky_refactor_preflight/recon.md --repo examples/gallery/risky_refactor_preflight/repo` |
| `agent_generated_patch_review` | Agent-generated profile patch를 allowlist evidence로 검토합니다. | `antemortem lint examples/gallery/agent_generated_patch_review/recon.md --repo examples/gallery/agent_generated_patch_review/repo` |
| `security_sensitive_change` | API key rotation 변경에서 high-severity authorization risk가 진행을 막습니다. | `antemortem lint examples/gallery/security_sensitive_change/recon.md --repo examples/gallery/security_sensitive_change/repo` |
| `missing_evidence_unresolved` | worker evidence가 없어 `NEEDS_MORE_EVIDENCE`가 나오는 경우입니다. | `antemortem lint examples/gallery/missing_evidence_unresolved/recon.md --repo examples/gallery/missing_evidence_unresolved/repo` |
| `ci_gate_blocking_merge` | `lint`는 통과하지만 `DO_NOT_PROCEED` artifact 때문에 `gate`가 merge를 막습니다. | `antemortem gate examples/gallery/ci_gate_blocking_merge/recon.md --repo examples/gallery/ci_gate_blocking_merge/repo` |

Gallery는 provider를 호출하지 않습니다. JSON artifact는 저장된 fixture이며, `lint`가 fixture repo와 대조해 검증합니다.

---

이 페이지는 [`antemortem-cli`](../README.md) 문서 모음의 일부입니다.
