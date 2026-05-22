# antemortem (CLI) — 쉬운 설명

> 짧은 소개입니다. README family: [English](README.md) · [한국어](README_KR.md) · [Easy](EASY_README.md) · [쉬운 한국어](EASY_README_KR.md)
> 생성된 source-of-truth claim block: [English](docs/generated/claims.md) · [Korean](docs/generated/claims_kr.md)
> 신뢰 모델: [한국어](docs/trust_model_kr.md) · [English](docs/trust_model.md)
> Toolkit positioning: [한국어](docs/toolkit_positioning_kr.md) · [English](docs/toolkit_positioning.md)
> Claim ledger: [한국어](docs/claim_ledger_kr.md) · [English](docs/claim_ledger.md)
> CLI examples: [한국어](docs/examples_kr.md) · [English](docs/examples.md)

## 무엇인가요?

Antemortem은 코드가 생기기 전에 구현 계획을 검사합니다. 사용자가 spec, 걱정되는 risk, 모델이 읽어도 되는 repo 파일을 먼저 적습니다. 그러면 각 risk를 `REAL`, `GHOST`, `NEW`, `UNRESOLVED` 중 하나로 분류하고, `lint`가 디스크에서 검증할 수 있는 citation을 요구합니다.

위험한 refactor, agent-generated patch, 구현 계획 merge, 큰 변경의 CI gate 전에 사용합니다.

일반적인 AI review는 diff나 chat에서 시작합니다. Antemortem은 더 앞 단계에서 시작합니다. 사람이 trap을 먼저 쓰고, 모델은 지정된 repo 파일 안에서만 근거를 찾으며, 검증되지 않는 citation은 실패로 처리됩니다.

## Trust loop

- `doctor`: 무엇을 읽고 보낼지 미리 봅니다.
- `run`: structured recon artifact를 씁니다.
- `lint`: schema, citation, evidence binding을 검증합니다.
- `evidence`: 기존 artifact의 누락된 evidence hash를 채웁니다.
- `eval`: offline golden case로 측정합니다.
- `gate`: CI에서 decision policy를 강제합니다.

## 7 commands

```bash
# 1. 템플릿에서 markdown doc 생성
antemortem init auth-refactor

# 2. provider 호출 전 preflight
antemortem doctor antemortem/auth-refactor.md --repo .

# 3. LLM 분류 실행
antemortem run antemortem/auth-refactor.md --repo .

# 4. 모든 file:line citation과 evidence hash를 디스크에서 검증
antemortem lint antemortem/auth-refactor.md --repo .

# 5. 기존 artifact의 누락 evidence hash 채우기
antemortem evidence antemortem/auth-refactor.json --repo . --write-missing

# 6. lint + decision allowlist로 CI gate
antemortem gate antemortem/auth-refactor.md --repo .

# 7. offline golden benchmark 평가
antemortem eval benchmarks/golden_cases --json
```

Optional critic mode: `antemortem run ... --critic`은 REAL/NEW finding을 두 번째로 검토합니다. 결과는 `CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE` 중 하나이며, 정책상 downgrade만 가능합니다.

## Evidence hash

유효한 citation은 있지만 hash가 없는 기존 artifact에는 `antemortem evidence <artifact.json> --repo . --write-missing`를 사용합니다. CI에서는 `antemortem lint <doc.md> --repo . --strict-evidence`로 모든 non-UNRESOLVED finding에 current hash가 있는지 강제합니다.

## Demo replay

```bash
PYTHONIOENCODING=utf-8 python examples/demo_replay.py
antemortem lint examples/demo_antemortem.md --repo .
```

Replay는 저장된 output을 사용합니다. API key와 network call이 필요 없습니다.
출력에는 `REAL`, `GHOST`, `NEW`, `UNRESOLVED`, final decision, lint verification이 포함되며, `tests/test_demo_replay.py`가 이 README 명령과 저장된 demo output의 일치를 확인합니다.

## Release check

```bash
python scripts/release_audit.py
```

Local readiness check입니다. build와 `twine check`를 실행하지만 publish는 하지 않습니다.

CI도 같은 offline trust check와 별도 wheel smoke job을 실행합니다. Provider API key는 필요 없습니다.

설치된 wheel entrypoint만 검증하려면:

```bash
python scripts/smoke_wheel_install.py
```

## Exit codes

Stable exit codes는 [CLI Exit Codes](docs/cli_exit_codes.md)에 정리되어 있습니다: `0` success, `1` validation failure, `2` usage/configuration error, `3` provider failure, `4` policy gate failure, `70` reserved internal error.

## 설치

```bash
pip install antemortem
```

PyPI 이름은 `antemortem`입니다. `antemortem-cli`가 아닙니다. Python 3.11+가 필요합니다.

## API keys

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # --provider anthropic 기본
export OPENAI_API_KEY=sk-...            # --provider openai
export GEMINI_API_KEY=...               # --provider gemini
```

OpenAI structured `parse` path를 구현한 OpenAI-compatible endpoint는 다음처럼 사용합니다.

```bash
antemortem run foo.md --repo . --provider openai --base-url https://... --model ...
```

로컬 또는 일부 compatible endpoint는 model별 structured-output fidelity가 다르므로 `antemortem lint`로 확인하십시오.

## 결과물

JSON artifact는 네 부분으로 구성됩니다.

1. **Classifications** — 사용자가 쓴 trap별 결과. `REAL`, `GHOST`, `NEW`, `UNRESOLVED`.
2. **New traps** — 사용자가 적지 않았지만 모델이 발견한 risk.
3. **Spec mutations** — 구현 전 spec에 반영할 구체적 수정.
4. **Decision gate** — `SAFE_TO_PROCEED`, `PROCEED_WITH_GUARDS`, `NEEDS_MORE_EVIDENCE`, `DO_NOT_PROCEED`.

CI는 enum으로 gate하고, 사람은 rationale을 읽습니다.

## 정직성을 만드는 guardrail

- **모델이 코드를 보기 전에 사람이 trap을 먼저 씁니다.** Anchoring을 줄이는 핵심 순서입니다.
- **UNRESOLVED가 아닌 모든 classification은 `file:line` citation을 가져야 합니다.** `antemortem lint`가 citation을 디스크 line bounds와 대조하고, `evidence_hash` / `evidence_snippet`이 있으면 cited text binding도 검증합니다.

둘 중 하나라도 없으면 검증되지 않은 plan review입니다. 둘 다 있으면 citation과 schema를 다시 확인할 수 있는 screening step입니다.

## 쓰지 말아야 할 때

- 오타, docstring, 한 줄 config처럼 recon 비용이 이득보다 큰 변경.
- 아직 spec이 없는 spike 단계.
- 빌드 시간이 recon 시간보다 짧은 아주 작은 변경.

## 1분 demo flow

```bash
antemortem init my-change
# antemortem/my-change.md 편집:
#   - Spec 작성
#   - Traps table에 최소 1개 row 추가
#   - Recon protocol에 최소 1개 파일 추가

antemortem doctor antemortem/my-change.md --repo .
antemortem run antemortem/my-change.md --repo .
antemortem lint antemortem/my-change.md --repo .
antemortem evidence antemortem/my-change.json --repo . --write-missing
antemortem gate antemortem/my-change.md --repo .
```

## 더 보기

- 전체 CLI 문서: [README_KR.md](README_KR.md)
- Methodology: [Antemortem repo](https://github.com/hibou04-ops/Antemortem)
- Schema 정의: `src/antemortem/schema.py`
- Decision gate 규칙: `src/antemortem/decision.py`

License: Apache 2.0. Copyright (c) 2026 hibou.
