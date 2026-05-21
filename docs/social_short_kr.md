antemortem-cli는 구현 전에 risk를 분류하는 CLI입니다.

사용자가 implementation plan, trap, 읽을 repo file을 먼저 적습니다. 도구는 risk를 REAL, GHOST, NEW, UNRESOLVED로 분류하고, `lint`가 schema, citation, evidence snippet, evidence hash를 disk 기준으로 검증합니다.

offline check 재현:

```bash
PYTHONIOENCODING=utf-8 python examples/demo_replay.py
antemortem lint examples/demo_antemortem.md --repo .
antemortem eval benchmarks/golden_cases --json
python scripts/check_repo_consistency.py
```

경계: AI code review 대체 주장이 아닙니다. adoption claim도 superiority claim도 하지 않습니다. benchmark는 repo-local fixture 기준입니다. citation은 grounding을 증명하지만 absolute truth를 증명하지 않습니다.

Docs: [launch_note_kr.md](launch_note_kr.md), [trust_model_kr.md](trust_model_kr.md), [release_hygiene.md](release_hygiene.md).
