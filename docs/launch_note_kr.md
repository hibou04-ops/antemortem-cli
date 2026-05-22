# Launch Note

`antemortem-cli`는 diff를 쓰기 전에 구현 계획의 risk를 점검하는 CLI/CI 도구입니다. 사용자가 spec, trap, 읽을 파일을 먼저 적고, 도구는 각 risk를 `REAL`, `GHOST`, `NEW`, `UNRESOLVED`로 분류합니다. `UNRESOLVED`가 아닌 finding은 repo 파일에 대한 citation이 있어야 합니다.

이 문서는 AI code review 대체를 주장하지 않습니다. 이 도구는 code review 전에, 구현 방향을 바꾸기 아직 쉬운 시점에 사용합니다.

## 검증 가능한 내용

- 구현 전 risk classification: [Trust Model](trust_model_kr.md)을 보십시오.
- repo-grounded citation과 evidence-bound check: `antemortem lint`로 검증합니다.
- offline golden benchmark: `antemortem eval benchmarks/golden_cases --json`로 재현합니다.
- release hygiene: `python scripts/release_audit.py`로 확인합니다.
- 공개 claim drift: `python scripts/check_repo_consistency.py`로 확인합니다.

## 로컬 재현 명령

```bash
pip install antemortem
antemortem --version
antemortem --help
```

provider 없이 demo replay를 실행합니다.

```bash
PYTHONIOENCODING=utf-8 python examples/demo_replay.py
```

checkout에서 offline verification을 실행합니다.

```bash
antemortem doctor examples/demo_recon.md --repo . --json
antemortem lint examples/demo_antemortem.md --repo .
antemortem eval benchmarks/golden_cases --json
python scripts/check_repo_consistency.py
python scripts/generate_readme_claims.py --check
```

publish 전에 release check를 실행합니다.

```bash
python scripts/release_audit.py
```

upload 전에는 dry run, upload 후에는 전체 post-release check를 실행합니다.

```bash
python scripts/post_release_check.py --version 0.10.2 --skip-pypi-network
python scripts/post_release_check.py --version 0.10.2
```

## 경계

- 이 문서는 superiority claim을 하지 않습니다.
- adoption 또는 production usage claim을 하지 않습니다.
- offline benchmark metric은 repo-local fixture 기준이며 일반 model score가 아닙니다.
- citation은 source text에 grounding되었음을 증명하지만 absolute truth를 증명하지 않습니다.
- provider behavior는 vendor, model, endpoint, refusal mode, structured-output fidelity에 따라 달라질 수 있습니다.
- 일반 offline check에는 provider API key가 필요하지 않습니다. `antemortem run`은 test stub이 아닌 경우 provider 설정이 필요합니다.

## 링크

- [Trust Model](trust_model_kr.md)
- [Evidence-bound citations](../README.md#evidence-bound-citations)
- [Benchmark-backed claims](../README.md#benchmark-backed-claims)
- [Repository self-checks](../README.md#repository-self-checks)
- [Release Hygiene](release_hygiene.md)
- [Post-Release Verification](post_release_verification.md)
