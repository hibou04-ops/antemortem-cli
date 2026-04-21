# antemortem-cli (한국어)

[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![PyPI](https://img.shields.io/badge/pypi-0.2.0-blue.svg)](https://pypi.org/project/antemortem/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](#상태--로드맵)
[![Tests](https://img.shields.io/badge/tests-68%20passing-brightgreen.svg)](tests/)
[![Methodology](https://img.shields.io/badge/methodology-Antemortem-blueviolet.svg)](https://github.com/hibou04-ops/Antemortem)

> **당신의 다음 feature 에는 7개의 리스크가 있습니다. 그중 5개는 상상 속에만 존재합니다. 2개는 아직 이름조차 붙지 않았습니다.**
>
> Antemortem 은 어느 것이 어느 것인지 — 코드에서, 15분 안에, lint 가 검증할 수 있는 file-and-line 인용과 함께 — 알려줍니다. diff 를 쓰기 전에.

```bash
pip install antemortem
```

English README: [README.md](README.md)

---

## 목차

- [이 도구가 해결하는 failure mode](#이-도구가-해결하는-failure-mode)
- [Worked example: 실제 ghost trap](#worked-example-실제-ghost-trap)
- [세 가지 커맨드](#세-가지-커맨드)
- [데이터 계약](#데이터-계약)
- [아키텍처](#아키텍처)
- [Non-trivial 한 설계 결정](#non-trivial-한-설계-결정)
- [이것은 아닙니다](#이것은-아닙니다)
- [비용 및 성능](#비용-및-성능)
- [검증](#검증)
- [3-layer stack](#3-layer-stack)
- [회의론자를 위한 FAQ](#회의론자를-위한-faq)
- [선행 연구 및 credit](#선행-연구-및-credit)
- [상태 및 로드맵](#상태--로드맵)
- [기여](#기여)
- [인용](#인용)
- [라이선스](#라이선스)

---

## 이 도구가 해결하는 failure mode

웬만큼 큰 변경은 다 똑같이 시작합니다. Spec 을 쓰고, 뭔가 잘못될 수 있는 것 몇 개를 적고, PR 을 엽니다. 그 다음 반나절 동안 다음을 발견합니다:

1. "리스크" 두 개는 실제로 존재하지 않았음. 코드가 이미 처리하고 있음.
2. 생각조차 못 한 리스크 하나가 load-bearing. 런타임에서 발견.
3. Spec 에 빠진 필드. 구현 중 압박 속에서 즉흥적으로 만들어냄.

이건 실력 문제가 아닙니다. 작업의 **모양** 자체가 그렇습니다: **종이에 쓴 계획은 코드를 읽지 않고는 스트레스 테스트될 수 없습니다.** 코드 리뷰는 PR 위에 있는 것을 잡고, 테스트는 본인이 테스트 해야겠다고 생각한 것을 잡습니다. 어느 쪽도 작성자가 첫 키 입력 전에 이미 구워넣은 실수를 잡지 못합니다.

Antemortem 은 그 스트레스 테스트입니다. 모델이 코드를 보기 전 본인 trap 을 enumerate 하고 (anchoring 방어), plan 과 관련 파일을 능력 있는 LLM 에 넘기면, 각 trap 에 대해 정확히 다음 중 하나를 받습니다:

| 라벨 | 의미 | 요구되는 증거 |
|---|---|---|
| `REAL` | 코드가 리스크를 확인함. 완화 없이는 변경이 깨지거나 regresses. | 실패가 surface 하는 `file:line`. |
| `GHOST` | 코드가 리스크를 반박함. 우려한 동작이 일어나지 않거나 기존 완화가 이미 처리. | 가설을 반박하는 `file:line`. |
| `NEW` | 사용자 리스트에 없던, 모델이 surface 한 리스크. | 해당 리스크를 드러내는 `file:line`. |
| `UNRESOLVED` | 제공된 파일에 어느 쪽 증거도 없음. 정직한 결과이지 실패 아님. | `null` (단, 설명 필수). |

두 가드레일이 이를 *"LLM 에게 내 plan 리뷰해줘"* 에서 discipline 으로 바꿔냅니다:

1. **모델이 코드를 보기 전 본인이 trap 을 enumerate.** 모델이 리스크 리스트를 frame 하지 못하게 — 본인이 함. Anchoring 을 source 단계에서 죽임.
2. **UNRESOLVED 가 아닌 모든 classification 이 `file:line` 인용 보유.** 스키마는 SDK 경계에서 Pydantic-enforced 이고, `antemortem lint` 가 모든 citation 을 disk 에서 재검증. 할루시네이트된 line number 는 build 를 fail 시킴.

이 두 가드레일 없이는 다른 형태의 hand-waving 으로 교환한 것뿐. **있으면**, 15분 안에 돌아가면서 테스트와 코드 리뷰가 못 잡는 에러 범주를 잡는 cheap 한 mechanical screening step 이 됩니다.

---

## Worked example: 실제 ghost trap

`omega_lock.audit` 서브모듈은 이 CLI 의 methodology 로 빌드됐습니다 (case study: [`hibou04-ops/Antemortem/examples/omega-lock-audit.md`](https://github.com/hibou04-ops/Antemortem/blob/main/examples/omega-lock-audit.md)). 초기 리스트에 7개 리스크. 15분짜리 recon 결과:

```
Trap t1: WalkForward 가 내부에서 fold 하므로 audit decorator 가 평가 비용을 이중으로 셈.
    Label:    GHOST
    Citation: src/omega_lock/walk_forward.py:82
    Note:     evaluate() 는 params 객체당 정확히 한 번 호출 — loop 없음, fold 없음.
              두려워한 O(n × folds) 비용이 존재하지 않음.
```

그 하나의 classification, 그 하나의 `file:line` 이 대략 **half-engineer-day** 를 절약. 두려워한 아키텍처 재작성은 잘못된 mental model 에 기반했던 것.

전체 결과:
- Ghost 1개 (위 trap t1)
- 리스크 downgrade 3개 (30–40% → 10–15%)
- 새 요구사항 1개 surface (`target_role` 필드, 구현 전 spec 에 추가)
- P(full spec ships on time): **55–65% → 70–78%**
- 구현: 1 engineer-day. 신규 20 tests 가 first run 에 통과.

Post-implementation 노트는 recon 이 *놓친* 것을 정직하게 기록 — 런타임에 surface 한 Windows cp949 터미널 인코딩 이슈. Antemortem 은 플랫폼 인코딩 이슈를 못 잡음. 이 admission 자체가 case study 의 일부; [methodology.md § Limits](https://github.com/hibou04-ops/Antemortem/blob/main/docs/methodology.md#limits) 참조.

---

## 세 가지 커맨드

### `antemortem init <name>`

공식 템플릿으로부터 문서를 스캐폴드. YAML frontmatter (`name`, `date`, `scope`, `reversibility`, `status`, `template`) + 7개 섹션 본문. `--enhanced` 는 더 풍부한 템플릿으로 교체: calibration 차원 (evidence strength, blast radius, reversibility), 세분화된 classification subtype (`REAL-structural`, `GHOST-mitigated`, `NEW-spec-gap`, …), 모든 REAL/NEW finding 에 대한 명시적 skeptic pass, decision-first output 구조.

```bash
antemortem init my-feature                  # basic
antemortem init prod-migration --enhanced   # 고-stakes 변경용
```

템플릿은 [Antemortem](https://github.com/hibou04-ops/Antemortem) 에서 MIT 로 vendoring.

### `antemortem run <doc>`

문서를 parse, spec + traps 테이블 + 나열된 파일 목록 추출, `--repo` 에서 파일 내용 load, frozen system prompt 와 함께 Anthropic API 호출, classifications 를 문서 옆 JSON audit artifact 에 쓰기 (`<doc>.json`).

| 관심사 | 선택 | 이유 |
|---|---|---|
| 모델 | 단일 Anthropic Claude 버전 코드에 pin | Classification + multi-file chain tracing 은 intelligence-sensitive. 모델 fallback 없음 — prompt contract 안정, 실행 간 동작 재현 가능. |
| 추론 | Adaptive thinking, `effort: high` | 모델이 제공하는 sampling 손잡이 (temperature / top_p / top_k) 는 pinned 버전에서 제거됨; prompting 이 대체. `high` effort 는 intelligence-sensitive 업무에 대한 벤더 권장 최소값. |
| 출력 형식 | `messages.parse(output_format=AntemortemOutput)` | SDK 경계에서 Pydantic 스키마 enforcement. 잘못 된 응답은 CLI 가 보기 전 `ValidationError` 로 raise. hot path 의 hand-written JSON parsing 없음. |
| 캐싱 | system prompt 에 `cache_control={"type": "ephemeral"}` | ~5k 토큰 system prompt 는 pinned 모델의 cacheable-prefix 최소값을 넘도록 설계됨, 5분 동일 window 내 반복 실행이 base input 비용의 ~0.1× 로 cache hit. CLI 는 매 call 에 `cache_read_input_tokens` 표시 — silent invalidator 가 loud fail 하게. |
| 파일 로딩 | `--repo` root, path-traversal 거부, UTF-8 + replace fallback | `../../etc/passwd` 로 나열된 파일은 warning 과 함께 skip. |

Markdown 문서 자체는 **수정되지 않습니다**. JSON artifact 가 machine-readable output 입니다. `lint` 가 artifact 를 disk 대조 검증합니다. 이 분리는 parsing bug 가 markdown 을 손상시키는 것을 막습니다.

### `antemortem lint <doc>`

CI 에 composable 한 두 단계 검증:

1. **Pre-run (schema)**: frontmatter parse, spec 섹션 텍스트 존재, 최소 하나의 trap enumerate, Recon protocol 아래 최소 하나의 파일. 모든 문서에 적용.
2. **Post-run (citations)**: 문서 옆 `<doc>.json` 존재 시 — 모든 input trap 에 classification, 모든 classification 에 유효한 `path:line` 또는 `path:line-line` 인용, 모든 인용 파일이 `--repo` 에 존재, 모든 line range 가 해당 파일의 bounds 내.

통과 시 exit `0`, 실패 시 `1`, 모든 violation 을 한 줄씩 출력. CI 게이트로: *"그 PR 의 antemortem 이 lint clean 하지 않으면 merge 불가."*

---

## 데이터 계약

이 CLI 가 생성하는 모든 artifact 는 Pydantic-validated. 데이터가 end-to-end 로 흐름:

```python
# Input: 사용자가 쓰는 markdown 문서
# ↓ parser.py
AntemortemDocument(
    frontmatter=Frontmatter(name=..., date=..., scope=..., status="draft"),
    spec="빌드하려는 변경...",
    files_to_read=["src/auth/middleware.py", "src/auth/token.py"],
    traps=[
        Trap(id="t1", hypothesis="쿠키에 저장된 세션 토큰이 refresh 시 rotate 안 됨", type="trap"),
        Trap(id="t2", hypothesis="동시 refresh 시 race condition", type="worry"),
    ],
)

# ↓ run.py → api.py → messages.parse(output_format=AntemortemOutput)
AntemortemOutput(
    classifications=[
        Classification(
            id="t1",
            label="REAL",
            citation="src/auth/middleware.py:45-52",
            note="Refresh 경로 (48번째 줄) 가 새 토큰을 발급하지만 기존 세션 쿠키는 건드리지 않음.",
        ),
        Classification(
            id="t2",
            label="GHOST",
            citation="src/auth/token.py:72",
            note="Refresh 함수가 mutate 전에 session lock 획득 — race window 없음.",
        ),
    ],
    new_traps=[
        NewTrap(
            id="t_new_1",
            hypothesis="Refresh 시 토큰 rotation 은 CDN 층 캐시 무효화 필요.",
            citation="src/auth/middleware.py:88",
            note="88번째 줄이 Cache-Control 설정하지만 token 으로 vary 안 함 — stale 토큰이 edge 캐시에 살아남음.",
        ),
    ],
    spec_mutations=[
        "추가: 토큰 rotation 시, 기존 세션 쿠키의 명시적 무효화.",
        "추가: Rotation 시퀀스에 CDN 캐시 무효화 단계.",
    ],
)

# ↓ lint.py 가 모든 citation 을 disk 에서 검증
# PASS — auth-refactor.md validates clean (schema + classifications)
```

모든 model 의 모든 필드는 Pydantic 에 의해 타입 체크됩니다. API 의 malformed 응답은 SDK 경계에서 `ValidationError` raise — artifact 를 오염시키지 않습니다. 파일에 존재하지 않는 줄을 가리키는 citation 은 `lint` 실패 — spec 을 오염시키지 않습니다.

---

## 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│  antemortem/my-feature.md  (markdown + YAML frontmatter)     │
└────────────────┬─────────────────────────────────────────────┘
                 │  parser.py (frontmatter + regex 섹션 분할)
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  AntemortemDocument (Pydantic)                               │
│    frontmatter · spec · files_to_read · traps                │
└────────────────┬─────────────────────────────────────────────┘
                 │  run.py (--repo 에서 파일 load, payload build)
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  api.py → client.messages.parse()                            │
│    thinking: adaptive, effort: high                          │
│    system=[SYSTEM_PROMPT + cache_control: ephemeral]         │
│    output_format=AntemortemOutput                            │
└────────────────┬─────────────────────────────────────────────┘
                 │  SDK 가 응답을 스키마 대조 검증
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  AntemortemOutput                                            │
│    classifications[]  (id, label, citation, note)            │
│    new_traps[]        (hypothesis, citation, note)           │
│    spec_mutations[]   (spec 에 대한 자유 형식 edit)           │
└────────────────┬─────────────────────────────────────────────┘
                 │  run.py 가 .md 옆에 JSON 쓰기
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  antemortem/my-feature.json  (audit artifact)                │
└────────────────┬─────────────────────────────────────────────┘
                 │  lint.py 가 .md 와 .json 양쪽 parse
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  citations.py → 모든 path:line 을 disk 에서 검증             │
│  exit 0 = classifications 신뢰 가능                          │
│  exit 1 = 뭔가 fabricated 이거나 out of date                 │
└──────────────────────────────────────────────────────────────┘
```

모든 모듈이 단일 책임; 파이프라인은 네트워크 없이 end-to-end 테스트 가능. `AntemortemDocument`, `Classification`, `NewTrap`, `AntemortemOutput` 이 데이터 계약 — 같은 타입이 `run` 에서 `lint` 까지 흐르므로 한쪽의 drift 가 다른 쪽에서 잡힘.

---

## Non-trivial 한 설계 결정

**단일 모델 pin, fallback 없음.** v0.2 에서 다중 모델 "지원" 은 vaporware. System prompt, 스키마, effort level, adaptive thinking 의 기대 동작 — 모두 모델-특정 계약. 다른 벤더 모델을 drop-in 하려면 이 모든 걸 re-tune 해야 함. v0.3 에서 `--model` flag 가 대안이 prompt contract 를 견디는지 검증한 뒤 도입될 때까지, pin 이 정직.

**Citation 은 `lint` 가 disk 에서 검증, 신뢰하지 않음.** Structured-output API 는 refusal 하에서 schema conformance 를 깰 수 있고, 잘 동작하는 모델도 긴 파일에서 가끔 line 을 miscount. 모델의 self-report citation 을 신뢰하는 것은 테스트된 PR 이 버그 없다고 믿는 것과 같은 실수. *유일한* 방어는 소스 대조 재검증. `lint` 는 `--strict` flag 가 아니라 first-class 커맨드 — CI 게이트가 ceremony 없이 돌릴 수 있어야 하므로.

**JSON artifact 가 출력, markdown 이 입력.** 모델이 markdown 을 in-place 로 편집할 수 있음 — 어떤 도구는 그렇게 함. 우리는 안 함, 세 가지 이유로: (1) markdown 은 당신 것이지 모델 것 아님; (2) 어느 방향이든 parse bug 가 수 시간의 작업을 corrupt 할 수 있음; (3) machine-readable JSON 은 downstream tooling (CI 게이트, 대시보드, diff 뷰어) 과 깔끔하게 compose. Markdown 은 human artifact 로 유지.

**~5k 토큰 system prompt, 의도적.** Pinned 모델은 cacheable-prefix 최소값을 넘는 prefix 를 ~0.1× read 비용에 cache. 더 짧으면 cache 안 됨; 더 길면 enforce 하는 discipline 으로부터 drift. 모든 substantive 바이트가 load-bearing: role framing, input format, 네 라벨의 정확한 정의, good/bad 예시가 있는 citation rule, anti-pattern 리스트, scope 경계, 네 개의 few-shot JSON 예시. [전체 prompt](src/antemortem/prompts.py) 는 prompt-cache-aware 설계 사례로 읽어볼 만.

**Pydantic v2 스키마가 데이터 계약, dict-모양 comment 아님.** `Classification`, `NewTrap`, `AntemortemOutput`, `Frontmatter`, `AntemortemDocument` 모두 end-to-end 흐름: SDK 가 API 경계에서 검증, `run` 이 검증된 JSON 을 쓰고, `lint` 가 load 시 검증. Malformed classification 은 disk 에 절대 쓰이지 않음 — 즉, main 에 merge 되지 않음.

**Windows path 정규화는 cache-invariant, cosmetic 아님.** `src\foo.py` 와 `src/foo.py` 는 disk 에서 같지만 API payload 에서는 다른 바이트 — cache key 는 byte-exact. content 가 build 되기 전 모든 path 는 forward slash 로 정규화. `api.py:_build_user_content` 참조. 3줄짜리 수정이 놓치면 100 run 당 ~\$15 silently 낭비.

**`run` 은 `ANTHROPIC_API_KEY` 없을 때 exit 2, 1 아님.** Exit code 는 CI 시스템과의 계약: `1` = content 문제 (사용자가 고쳐야, "내 antemortem 에 이슈가 있음"), `2` = 환경 문제 (operator 가 고쳐야, "secret 이 빠짐"). 섞이면 CI triage 어려워짐.

**Scope 경계는 prompt 에서 enforced, 제안 아님.** System prompt 는 명시적으로 말함: *"You classify what is in the provided files. You do not: speculate about files not shown, comment on architecture beyond the spec's scope, recommend the user adopt a different design, evaluate whether the change is a good idea."* 사용자가 위 중 하나를 요청하면 모델은 `spec_mutations` 에 "Out of antemortem scope" 로 기록하고 진행하도록 지시받음. 이 도구는 한 가지만 함.

**Hard-wired UTF-8 + replace fallback.** 비-UTF-8 파일이 도구를 crash 시키지 않음. 바이트 수준 교체와 warning 으로 읽힘. "YAML 파일의 BOM 때문에 내 antemortem 이 실패했습니다" 와 "내 antemortem 이 돌았고 그 파일에 대한 minor note 를 포함했습니다" 의 차이.

---

## 이것은 아닙니다

잘못된 용도로 쓰면 discipline 이 실패. 명시적 non-goals:

| 이 도구는 | 이유 |
|---|---|
| 코드 리뷰 대체가 아님 | 코드 리뷰는 쓰여진 diff 를 봄. Antemortem 은 *아직 존재하지 않는* diff 의 *부재* 를 봄. 다른 단계. 둘 다 필요. |
| 디자인 리뷰가 아님 | 디자인 리뷰는 "이거 만들어야 하나?" 를 물음. Antemortem 은 그 답이 yes 라고 가정하고 "기존 코드가 리스크에 대해 이미 뭘 말하는가?" 를 물음. |
| 런타임 버그 탐지기가 아님 | Race condition, GC timing, 네트워크 flake, 플랫폼 인코딩 — 이들은 파일 바깥에 있음. Antemortem 은 못 잡음. [Limits](https://github.com/hibou04-ops/Antemortem/blob/main/docs/methodology.md#limits) 참조. |
| LLM "세컨드 오피니언" 챗봇이 아님 | 두 가드레일 (enumerate-first, cite-every-line) 없이는 LLM 이 당신이 쓴 것에 기꺼이 동의. 이 CLI 가 enforcement mechanism. |
| LLM 코딩 능력 벤치마크가 아님 | Classification 은 citation 만큼만 신뢰 가능, `lint` 가 재검증. 여기서 측정되는 건 *discipline* 이지 모델이 아님. |
| 테스트 대체가 아님 | 테스트는 동작 검증. Antemortem 은 본인 mental model 을 소스와 대조 검증. 변경은 둘 다 pass 해야 함. |

위 중 하나로 이 도구를 쓰고 있다면 잘못 쓰고 있는 것. 잘못된 사용의 비용은 낭비된 call, 그리고 더 나쁘게는 false confidence.

---

## 비용 및 성능

현재 Anthropic frontier-model 가격 기준 run-당 비용 (전형적 워크로드):

| 시나리오 | 캐시 동작 | 추정 비용 |
|---|---|---|
| 하루 첫 실행 | System prompt 가 cache 에 write (write premium) | ~\$0.15–0.20 |
| 5분 내 동일 prompt 반복 실행 | System prompt cache read (~0.1×) | ~\$0.10–0.12 |
| 활발한 개발 중 100 회 반복 | Write + read 혼합 | \$10–20 |

매 `run` 이 토큰 breakdown — `input (+cache_read, +cache_write) output` — 을 출력하므로 매 호출에서 cache 가 engage (또는 silently fail) 하는지 볼 수 있음. prompt 가 동일한데도 연속 실행에서 `cache_read_input_tokens` 가 0 이면, prompt 빌드 파이프라인 어딘가에 silent invalidator — CLI 가 명시적으로 경고 출력.

기본 `--max-tokens` 는 16000. 전형적 output 은 1–4k. 큰 surface 의 드문 deep recon 을 위해 128000 까지 올릴 수 있음.

---

## 검증

**68 tests, CI 에서 네트워크 호출 0.** Anthropic client 는 `api.py` 의 `Protocol` 인터페이스로 받음, 모든 API 테스트는 `SimpleNamespace` 나 `MagicMock` 으로 응답 mock. 두 가지 benefit: API 크레딧 소비 없는 결정론적 CI, 그리고 실제 서버와 협상 없이 request payload 의 *정확한* shape (model, thinking config, cache_control 배치, 정렬된 파일 순서) 을 assert 할 수 있는 테스트-시점 자유도.

| 모듈 | 커버리지 |
|---|---|
| `schema.py` | 9 tests — 필수 필드, label enum, UNRESOLVED 의 nullable citation, NewTrap id pattern, JSON roundtrip. |
| `citations.py` | 13 tests — range 파싱, Windows backslash 정규화, 빈 문자열 / prose / zero-line / reversed-range 거부, path traversal 포함 disk 검증. |
| `parser.py` | 12 tests — frontmatter 검증, 섹션 추출, `recon-protocol` vs `pre-recon` 구분, placeholder-row 필터링과 trap 테이블 파싱. |
| `lint.py` | 11 tests — 두 단계 (schema-only 와 artifact), 모든 violation 경로, exit code. |
| `api.py` | 5 tests — payload shape, 파일 정렬 결정성, refusal branch, parsed-output 계약, dict-fallback coercion. |
| `run.py` | 7 tests — 모킹된 client 로 전체 흐름, 에러 경로, 경고, JSON-summary env var. |
| `init.py` | 6 tests — basic + enhanced 템플릿, `--force`, path traversal 거부, ISO 날짜 frontmatter. |
| `cli.py` | 5 tests — `--help`, `--version`, no-args-prints-help. |

`uv run pytest -q` 로 실행. 전형적 wall time: 0.2s.

---

## 3-layer stack

이 CLI 는 point tool 이 아니라 layered discipline 의 3번째 tier:

```
         ┌─────────────────────────────────────────────┐
 Layer 3 │  antemortem-cli  (this repo)                │  "Discipline 을 실행"
         │  0.2.0 — CLI + PyPI + schema + lint         │
         └────────────────────┬────────────────────────┘
                              │ operationalizes
                              ▼
         ┌─────────────────────────────────────────────┐
 Layer 2 │  Antemortem  (methodology)                  │  "Discipline 을 정의"
         │  v0.1.1 — 프로토콜, 템플릿, case studies    │
         └────────────────────┬────────────────────────┘
                              │ demonstrated by
                              ▼
         ┌─────────────────────────────────────────────┐
 Layer 1 │  omega-lock  (reference implementation)     │  "Shipped 증거"
         │  0.1.4 — Python calibration audit framework │
         └─────────────────────────────────────────────┘
```

- **[omega-lock](https://github.com/hibou04-ops/omega-lock)** — Python calibration framework, Antemortem discipline 이 *처음 실제로 practice 된* 프로젝트. `omega_lock.audit` 서브모듈이 위에 기록된 ghost trap 을 잡은 15분짜리 antemortem recon 으로 빌드됨.
- **[Antemortem](https://github.com/hibou04-ops/Antemortem)** — 그 빌드에서 결정화된 methodology: 7-step 프로토콜, basic 과 enhanced 템플릿, 첫 case study. Docs-only.
- **antemortem-cli** (이 repo) — 마찰을 제거하는 도구: `init` 으로 스캐폴드, `run` 으로 classify, `lint` 로 verify. 세 커맨드, 하나의 데이터 계약, disk-verified citation.

네 번째 repo **[omegaprompt](https://github.com/hibou04-ops/omegaprompt)** 는 omega-lock 의 calibration engine 을 prompt engineering 에 적용 — discipline 패턴이 도메인을 넘어 transfer 됨을 보여줌.

Layering 은 정확성에 중요: methodology 는 CLI 빌드 *전에* 실제 shipped artifact (omega-lock 0.1.4 on PyPI, 176 tests) 로 검증됨. 도구는 이미 작동하는 걸로 알려진 프로토콜을 automate — 도구와 나란히 발명된 프로토콜이 아님.

---

## 회의론자를 위한 FAQ

**이건 그냥 pre-mortem (Klein, 2007) 을 새 이름으로 한 것 아닌가요?**

아닙니다. Gary Klein 의 pre-mortem 은 *팀-수준 전략적 연습* ("우리가 실패했다고 가정; 원인은?") 으로 프로젝트 commit 시점에 30–60분 소요. Antemortem 은 *change-수준, 솔로, 소스-코드-기반, 전술적*, 15–30분에 discharged. Pre-mortem 은 *"해야 하나?"* 를 묻고, Antemortem 은 *"할 것이니, 기존 코드가 이 특정 접근의 리스크에 대해 이미 뭘 말하는가?"* 를 물음. 그들은 compose — pre-mortem 먼저, antemortem 은 per-change.

**그냥 Claude 에게 "내 spec 리뷰해줘" 하면 되지 않나?**

그게 이 도구가 방지하려는 degenerate case. 두 가드레일 없이는 LLM 이 당신이 쓴 것에 기꺼이 동의. 일반적 리스크와 진짜 리스크가 섞인 리스트를 받고, 어느 게 어느 건지 구분할 수 없고, 모델이 주장을 뒷받침하도록 압박이 없음. `file:line` 요구 + `lint` 의 재검증이 "의견" 과 "증거" 의 차이.

**모델이 line number 를 그냥 지어낼 건데?**

가끔 그럴 것. 그래서 `lint` 가 존재. 모든 citation 이 parsed, 파일이 load, line range 가 실제 파일 bound 와 대조. 할루시네이트된 citation 은 lint fail. 모델은 *"A fabricated line number is strictly worse than UNRESOLVED — UNRESOLVED is honest, fabrication is not"* 라고 지시받고, discipline 이 mechanical 검증으로 이를 backup.

**비공개/private 코드에서 작동하나요?**

네. LLM 은 당신이 주는 걸 읽음; public repo 필요 없음. 유일 제약은 공개 case study 의 citation 은 repo 없이도 readers 가 verify 할 수 있도록 inline context 를 충분히 quote 해야 함.

**IDE 플러그인은? Web UI 는?**

v0.2 범위 밖. CLI 가 CI-gate 도구에 맞는 surface — GitHub Actions, pre-commit hook, 로컬 Makefile 에서 `antemortem lint` 가능. Web UI 는 state + auth 추가; 플러그인은 IDE 확장 API 에 coupling. 둘 다 primary use case (merge-gate) 에 더 나쁨.

**Go / Rust / TypeScript 인데 쓸 수 있나요?**

네. Antemortem 은 언어-agnostic — Python AST 가 아니라 *파일* 을 읽음. CLI 는 Python 패키지지만 target repo 는 아무거나. Case study 는 Python; discipline 은 Rust crate 나 TypeScript monorepo 에서도 같게 작동.

**Cursor / Claude Code / Aider 의 "plan" 모드와 어떻게 다른가요?**

그 도구들은 planning 을 편집 loop 에 통합 — 유용하지만, plan 이 구현과 같은 세션에 있음. Antemortem 은 보존할 *별도 artifact*. 6개월 후 feature 가 당신을 놀라게 했을 때, `antemortem/auth-refactor.md` 를 다시 읽고 어떤 가정이 깨졌는지 볼 수 있음. Ephemeral chat 이 아니라 disciplined paper trail.

**왜 Python 인가요?**

첫 사용자가 omega-lock (Python) 위에 빌드하고 있었기 때문, 그리고 Anthropic SDK 가 structured output 에 대해 가장 타이트한 Python ergonomics 가지므로. 이 도구는 100% offline-validatable (`lint` 는 네트워크 필요 없음) 이라 Python 런타임이 hot-path 제약이 아님.

---

## 선행 연구 및 credit

이 도구가 서 있는 두 아이디어:

- **Pre-mortem** — Gary Klein, *"Performing a Project Premortem"*, Harvard Business Review, 2007년 9월. 아이디어의 팀-전략적 버전.
- **Winchester defense** — 원래 quant-finance discipline: *kill criteria 는 run 전에 선언되어야 하고, 이후에 완화될 수 없음*. 여기선 `lint` 가 self-report 에 의존하지 말고 gate 시점에 citation 을 mechanical 로 검증해야 함을 주장하는 데 사용. Parameter-calibration analog 는 omega-lock 의 [`docs/methodology.md § Kill criteria`](https://github.com/hibou04-ops/omega-lock/blob/main/src/omega_lock/kill_criteria.py) 참조.

네이밍은 명시적: *postmortem* (죽음 후) → *antemortem* (죽음 전). Methodology 는 2026년 4월 `omega_lock.audit` 서브모듈 빌드 중 emerge 했고 [hibou04-ops/Antemortem](https://github.com/hibou04-ops/Antemortem) 에 문서화.

---

## 상태 & 로드맵

v0.2.0 은 **alpha**. CLI 계약 (세 커맨드, flag, exit code) 은 stable. Prompt 는 다양한 실제 repo 에서 classification 품질 데이터가 축적되면서 iterate — v0.2.x bump 는 prompt 수정 용도, CHANGELOG 의 *"Prompt revisions"* 섹션에 추적. JSON artifact 스키마는 v0.2.x 내에서 stable; 스키마 breaking change 는 v0.3 cut.

Semver 는 v1.0 부터 엄격 적용.

**v0.2.x (prompt iteration 트랙)**
- 다양한 실제 repo (Python, TypeScript, Go) 에 dogfood. Classification 에러가 군집하는 곳을 찾아 anti-pattern 리스트 tune.
- Reference classification-quality benchmark 기록해서 prompt 개정을 추측이 아니라 측정으로.

**v0.3 (도구 깊이)**
- 반복 same-repo run 을 위해 files block 에 두 번째 `cache_control` breakpoint.
- `antemortem diff` — 같은 doc 의 두 run 을 비교, 어떤 classification 이 이동했는지 surface.
- JSON artifact 의 HTML renderer (printable debrief view).
- Prompt 가 model swap 을 견딜 만큼 안정화되면 Optional `--model` flag.

**v1.0 (계약 lock)**
- Public schema 버저닝 (`antemortem.schema.json` 별도 publish).
- Output JSON shape 의 semver 보장.
- CI lint gating 용 공식 GitHub Action.

**명시적 out of scope** (v0.2 이후 포함): 웹 대시보드, DB-backed 히스토리, 멀티유저 tenancy, proprietary hosting.

전체 changelog: [CHANGELOG.md](CHANGELOG.md).

---

## 기여

Case study 는 [Antemortem methodology repo](https://github.com/hibou04-ops/Antemortem) 의 `examples/` 아래 PR 로 — 가장 가치 있고 가장 만들기 어려운 기여. Bar: *"모든 classification 이 `file:line` 인용, post-implementation 노트 존재, recon 이 놓친 것에 정직할 것."*

도구 레벨 기여 (새 CLI flag, 스키마 필드, prompt 수정) 는 이 repo 의 `main` 대상 PR. 가능하면 해당 변경에 대한 antemortem 문서 첨부 — 도구는 자기 자신의 개발에 dogfood 됨.

---

## 인용

```
antemortem-cli v0.2.0 — tooling for the Antemortem pre-implementation reconnaissance discipline.
https://github.com/hibou04-ops/antemortem-cli, 2026.
```

Methodology:
```
Antemortem v0.1.1 — AI-assisted pre-implementation reconnaissance for software changes.
https://github.com/hibou04-ops/Antemortem, 2026.
```

---

## 라이선스

MIT. [LICENSE](LICENSE) 참조.

## Colophon

Solo 로 설계, 구현, ship. 7개 모듈, 68 tests, CI 에서 live API 호출 0. 이 도구는 자신을 build 하는 변경사항들을 classify — dogfood 가 first-class 테스트 surface.
