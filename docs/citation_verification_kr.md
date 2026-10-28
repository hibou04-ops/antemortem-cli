# 인용 검증: 파일 읽기·근거·이행 안내

`verified`는 저장소 내부 경로와 인용 라인의 존재, 제공된 hash·snippet과 현재 텍스트의 일치를 확인합니다. 텍스트가 주장을 논리적으로 뒷받침하는지, 주장이나 프로그램이 올바른지는 검증하지 않습니다. 호환 JSON 분류명 `fabricated`는 잘못된 형식·없는 파일·범위 오류·오래된 hash·불일치 snippet·읽기 실패·관측된 파일 변경을 포함합니다. 원인은 `reason`으로 구별하며 의도적 조작을 판정하지 않습니다. `unresolved`는 별도로 유지합니다.

## 같은 실행 안에서만 읽기를 재사용

CLI lint/gate의 검사와 JSON metrics는 하나의 `CitationVerifier`를 공유합니다. metrics와 CLI/MCP run의 hash 부착·사전 audit도 실행 단위로 재사용합니다. 다음 명령은 새로 읽으므로 이전 실행의 성공을 보관하지 않습니다.

매 접근에서 경로와 symlink를 다시 해석하고 저장소 경계·일반 파일 여부·파일 식별자·크기·나노초 수정 시간을 확인합니다. 읽기 전후 파일 descriptor와 경로 정보도 비교합니다. POSIX에서는 ctime도 비교합니다. Python 3.12 Windows의 stat/fstat는 legacy ctime의 의미가 달라질 수 있어 Windows에서는 이를 직접 비교하지 않습니다. 변경을 발견하면 같은 실행 안에서는 해당 파일을 실패로 처리합니다. 접근 거부와 읽기 실패도 설명 가능한 검증 실패입니다.

기본 8 MiB 한도는 캐시된 텍스트와 라인 tuple에 적용됩니다. 결과 출력과 파일별 메타데이터는 이 한도 밖입니다. 한도를 넘는 파일은 순회하며 요청 범위만 보관할 수 있습니다. 큰 파일의 서로 다른 범위는 재순회할 수 있으므로 모든 입력의 I/O나 전체 메모리가 일정하다는 주장이 아닙니다. 기존 provider 파일 읽기 제한과 근거 범위 제한은 유지합니다.

이 기능은 일반적인 동시 편집을 탐지합니다. 저장소의 원자적 snapshot이나 모든 메타데이터를 복원하는 공격에 대한 방어를 보장하지 않습니다. 고정된 재현성이 필요하면 입력 checkout을 동결하세요.

## 실제 전후 결과

공개 기준선은 `antemortem==0.11.2`, commit `95a49e75a03b2289c1015b72b09cbc4cfbae8310`입니다. 시작 HEAD와 최신 Release가 같았으며 미발행 변경의 효과를 포함하지 않았습니다. Windows 11·Python 3.12.10의 분리된 가상환경에서 비교했습니다. provider 호출은 없습니다.

[`scripts/benchmark_citation_io.py`](../scripts/benchmark_citation_io.py)는 실행 전에 2,000줄 UTF-8 파일·1/20/200 findings·서로 다른 열 개 범위·일치 hash·입력당 한 번의 명령을 고정합니다. 실제 source `Path.open`을 셉니다. lint/gate JSON의 metrics 계산까지 포함하고 입력 생성·문서/artifact 읽기·설치 비용은 source 열기 횟수에서 제외합니다. 전체 실행 배속은 측정하지 않았습니다.

| 인용 수 | metrics 파일 열기: 이전 → 개선 | lint/gate JSON 파일 열기: 이전 → 개선 |
|---:|---:|---:|
| 1 | 2 → 1 | 4 → 1 |
| 20 | 40 → 1 | 80 → 1 |
| 200 | 400 → 1 | 800 → 1 |

모든 workload에서 검증 건수와 성공 종료 코드를 유지합니다. 알려진 개발 회귀 사례 10건에서는 올바른 판정이 7건에서 10건으로 바뀌었습니다. 이전 metrics는 잘못된 snippet과 오래된 legacy hash를 통과시켰고, vertical tab이 있으면 라인 검증과 hash의 텍스트 선택이 달랐습니다. 수정에 사용한 사례이며 새 blind 평가나 일반 환경 정확도 추정이 아닙니다.

별도로 변경·삭제·이동·접근 거부·잘못된 UTF-8·LF/CRLF/CR·캐시 축출·symlink 경계 사례를 검사합니다. Windows에서 symlink 생성 권한이 없으면 해당 검사는 skip되며 기존 Linux CI에서도 실행합니다. [원시 결과와 환경](citation_io_results.json).

## 호환성과 이행

- 기존 JSON schema·필드·MCP 도구명·CLI 종료 코드의 의미를 유지합니다.
- metrics와 runtime audit가 제공된 legacy hash·snippet·근거 범위 제한을 lint와 같은 규칙으로 검사합니다. 이전의 잘못된 통과가 실패로 바뀔 수 있습니다. `reason`을 확인하고 artifact를 재생성·재검토하세요.
- LF·CRLF·CR만 라인 구분으로 사용합니다. VT·FF·Unicode paragraph separator는 라인 내부 문자입니다. 해당 문자가 있는 이전 artifact는 다시 생성해야 할 수 있습니다.
- 이전 artifact의 근거 필드는 여전히 선택 사항입니다. `--strict-evidence`를 요청하면 현대식 `evidence_hash`가 필요합니다.
- lint/gate의 검증 실패는 exit 1, gate의 정책 차단은 exit 4, 잘못된 옵션은 exit 2입니다. metrics는 `--fail-over` 없이 실패 내용을 보고해도 exit 0입니다. `--fail-over 0`이면 fabricated가 하나라도 있을 때 exit 4입니다. 명령 실행 성공과 품질 통과를 구별하세요.
- `omega-lock` 런타임 의존성은 추가하지 않았고 기존 CI의 고정 소스 SHA는 유지합니다.

정확한 비교 방법과 Python API 예제는 [영문 문서](citation_verification.md)에 있습니다. source checkout 밖에서 각 설치 환경의 Python으로 benchmark script를 실행하면 전후 비교를 재현할 수 있습니다.
