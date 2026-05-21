# Toolkit Positioning

`antemortem-cli`는 이 toolkit 안에서 CLI와 CI 검증을 맡는 도구입니다. 범위는 좁게 유지합니다: 구현 전 reconnaissance, 코드 변경 전 risk classification, citation/evidence가 검증된 CLI artifact입니다.

이 저장소는 dashboard, SaaS control plane, 범용 agent framework를 포함하지 않습니다.

## 이 저장소의 역할

`antemortem-cli`가 답하려는 질문은 다음입니다.

> diff를 쓰기 전에, 이 구현 계획의 리스크는 `REAL`, `GHOST`, `NEW`, `UNRESOLVED` 중 무엇이며 그 판단을 지지하는 source line은 어디인가?

로컬 trust boundary는 다음과 같습니다.

- `doctor`: provider 호출 전에 파일, trap parsing, payload를 미리 보여줍니다.
- `run`: structured recon artifact를 만듭니다.
- `lint`: schema, citation, path bounds, snippet, evidence hash를 디스크와 대조합니다.
- `evidence`: 로컬 evidence hash를 재계산하거나 누락분만 채웁니다.
- `eval`: committed offline golden case로 동작을 측정합니다.
- `gate`: CI에서 decision policy를 강제합니다.

## 관련 도구

아래 이름은 인접한 역할을 설명하기 위한 것입니다. adoption, production usage, external validation을 주장하지 않습니다.

| Tool | 중립적 역할 | 경계 |
|---|---|---|
| `omegaprompt` | Calibration / optimization layer | Prompt와 workflow calibration에 해당합니다. `antemortem lint`나 `gate`를 대체하지 않습니다. |
| `omega-lock` | Audit / post-optimization lock layer | Calibration 이후 audit 기준과 lock 상태를 다룹니다. 이 저장소의 pre-diff risk classifier가 아닙니다. |
| `mini-omega-lock` | Empirical live API preflight | network/provider 접근이 명시적으로 가능한 경우의 live API behavior check입니다. 이 저장소의 deterministic offline test path 밖에 있습니다. |
| `mini-antemortem-cli` | Deterministic analytical preflight | 사용한다면 좁은 analytical preflight 표면입니다. 이 저장소에서 배포하는 CLI/CI 도구는 아닙니다. |
| `omega-plc.com` | Link-only external surface | [https://www.omega-plc.com/](https://www.omega-plc.com/) 링크만 제공합니다. 이 링크만으로 SaaS capability를 주장하지 않습니다. |

## 조합 방식

보수적인 조합은 다음 순서입니다.

1. Prompt나 workflow calibration이 문제라면 `omegaprompt`를 사용합니다.
2. 질문이 더 좁은 preflight와 맞을 때만 `mini-*` 도구를 사용합니다.
3. 코드 변경 전 계획 리스크를 citation과 evidence로 분류해야 하면 `antemortem-cli`를 사용합니다.
4. Optimization/audit 이후 기준이나 audit state를 고정해야 하면 `omega-lock`을 사용합니다.

각 도구는 서로 다른 단계를 맡습니다. 이 저장소는 로컬과 CI에서 검증 가능한 CLI artifact에 집중합니다.

## Claim 경계

이 문서는 다음을 주장하지 않습니다.

- enterprise adoption
- production usage
- external validation
- 다른 도구 대비 comparative quality
- 위 link-only reference 이상의 SaaS behavior

이 저장소의 공개 claim은 source-of-truth generation, deterministic tests, committed artifacts, 또는 reproducible commands로 뒷받침되어야 합니다.

## Link verification

offline CI 경로에서는 network link check를 수행하지 않습니다. 로컬 positioning link와 external allowlist는 다음 테스트가 확인합니다.

```bash
python -m pytest tests/test_toolkit_positioning_docs.py -q
```

더 넓은 repository check는 다음 명령으로 실행합니다.

```bash
python scripts/check_repo_consistency.py
```
