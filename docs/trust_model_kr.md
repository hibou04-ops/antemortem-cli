# 신뢰 모델

`antemortem-cli`는 diff가 생기기 전에 구현 계획의 리스크를 저장소의
근거와 대조하는 CLI/CI 도구입니다. 입력 문서에 변경 내용, 사용자가
예상한 trap, 모델이 읽어도 되는 파일이 명시되어 있을 때만 의미가
있습니다.

## 무엇을 검증하는가

- recon 문서가 파싱되는지 확인합니다: frontmatter, spec, trap table, file list.
- 요청된 파일이 repository root 안에 있고 file-safety policy를 통과하는지 확인합니다.
- provider output이 기록되기 전에 Pydantic schema를 만족하는지 검증합니다.
- `UNRESOLVED`가 아닌 finding이 disk에서 검증 가능한 `path:line` 또는
  `path:line-line` citation을 갖는지 확인합니다.
- 선택 필드인 `evidence_snippet`과 `evidence_hash`가 cited source text와 맞는지 확인합니다.
- decision gate가 artifact에서 결정론적으로 계산되고 CI에서 강제될 수 있는지 확인합니다.
- offline golden case가 현재 repo-local benchmark metric을 계속 재현하는지 확인합니다.

## 무엇을 검증하지 않는가

- 모델이 모든 리스크를 찾았다는 것을 증명하지 않습니다.
- 구현 계획 자체가 전략적으로 옳다는 것을 증명하지 않습니다.
- runtime behavior, security, performance, platform behavior를 증명하지 않습니다.
- cited claim이 절대적으로 참이라는 것을 증명하지 않습니다. Citation은 source
  location에 grounded 되어 있음을 보일 뿐, 전체 진실성을 보장하지 않습니다.
- provider와 model 간 behavior가 같다는 것을 보장하지 않습니다.
- repo-local benchmark metric이 다른 저장소에도 일반화된다고 주장하지 않습니다.

## 왜 사용자가 trap을 먼저 쓰는가

사용자가 trap을 먼저 쓰고, 그 다음에 모델이 코드를 봅니다. 이것이
anchoring control입니다. 모델은 사용자가 선언한 리스크를 `REAL`,
`GHOST`, `UNRESOLVED`로 분류하고, 저장소 근거가 있을 때만 `NEW` finding을
추가할 수 있습니다. 이렇게 해야 모델이 risk list 자체를 처음부터 frame하지
못하고, 빠진 항목이 보입니다. 사용자가 trap을 쓰지 않았고 모델도 `NEW`로
surface하지 않았다면, 이 도구는 그 리스크가 검토되었다고 주장할 수 없습니다.

## Citation validation

`lint`는 provider citation을 사실로 믿지 않고 검증할 claim으로 취급합니다.
`path:line`과 `path:line-line` citation을 파싱하고, `--repo` 아래에서 path를
resolve하며, symlink나 reparse point를 따라간 뒤 repository root 밖으로
나가는 경로를 거부합니다. 대상이 regular file인지 확인하고 line range가
파일 범위 안에 있는지도 검사합니다. `UNRESOLVED` classification은 반드시
`citation: null`이어야 합니다.

## Evidence hash

Line bounds는 cited location이 존재한다는 것을 보입니다. Evidence hash는
artifact를 cited source text에 묶어서 source drift를 줄입니다. 도구는 cited
text의 줄바꿈을 LF로 정규화하고 trailing whitespace만 제거한 뒤 SHA-256을
로컬에서 계산해 `sha256:<hex>` 형식으로 저장합니다. 이후
`lint --strict-evidence`가 hash를 다시 계산하고, cited source가 바뀌었으면
실패합니다. 모델에게 hash를 만들라고 요구하지 않습니다. `antemortem run`과
`antemortem evidence --write-missing`이 citation validation 이후 로컬에서
계산합니다.

## Offline golden benchmark

Benchmark harness는 committed golden case와 저장된 provider output을 사용합니다.
Network call을 하지 않고 provider SDK client도 만들지 않습니다. 목적은 회귀
탐지입니다. Classification label, citation validity, decision quality, schema
parsing, critic-pass impact를 repo-local fixture에 대해 측정합니다. 이 metric은
local claim을 뒷받침할 뿐이며, 다른 도구와의 비교 품질 claim이나 임의의
저장소에 대한 성능 claim이 아닙니다.

## Provider output은 lint 전까지 신뢰하지 않는다

Provider output은 malformed, partial, safety-blocked, 또는 overconfident일 수
있습니다. `run`은 artifact를 쓰기 전에 schema와 classification coverage를
검증합니다. 그래도 CI에서 evidence로 쓰기 전에는 `lint`를 통과해야 합니다.
저장소를 다시 열고 citation, evidence snippet, hash를 disk와 대조하는 단계는
`lint`이기 때문입니다.

## CI 사용 방식

명령은 분리해서 사용합니다.

```bash
antemortem doctor antemortem/my-feature.md --repo .
antemortem lint antemortem/my-feature.md --repo . --strict-evidence
antemortem eval benchmarks/golden_cases --json
antemortem gate antemortem/my-feature.md --repo .
```

`doctor`는 provider 호출 없는 preflight입니다. `lint`는 schema, citation,
evidence를 검증합니다. `eval`은 offline benchmark harness를 확인합니다.
`gate`는 artifact의 decision policy를 강제합니다. 일반 CI는 의도적으로 live
`antemortem run`을 실행하지 않는 한 provider API key가 필요하지 않아야 합니다.

## 알려진 한계

- 모델은 리스크를 놓칠 수 있습니다.
- Benchmark case는 repo-local fixture이며 일반적인 model score가 아닙니다.
- Citation은 source text에 grounded 되어 있음을 보일 뿐 absolute truth를 증명하지 않습니다.
- Provider behavior는 vendor, model, endpoint, refusal mode, structured-output
  fidelity에 따라 달라질 수 있습니다.

---

이 페이지는 [`antemortem-cli`](../README.md) 문서 모음의 일부입니다.
