# antemortem-cli (한국어)

[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![PyPI](https://img.shields.io/badge/pypi-0.2.0-blue.svg)](https://pypi.org/project/antemortem/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](#status)
[![Tests](https://img.shields.io/badge/tests-68%20passing-brightgreen.svg)](tests/)
[![Methodology](https://img.shields.io/badge/methodology-Antemortem-blueviolet.svg)](https://github.com/hibou04-ops/Antemortem)

> **소프트웨어 변경을 위한 사전 정찰 (Pre-implementation reconnaissance).**
> diff 를 작성하기 *전에* 실제 코드에 대해 계획을 스트레스 테스트 하세요. 15분. `file:line` 인용. Pydantic 스키마가 허위 인용을 lint 단계에서 실패시킵니다.

```bash
pip install antemortem
```

English README: [README.md](README.md)

---

## 목차

- [이게 왜 필요한가](#이게-왜-필요한가)
- [30초 데모](#30초-데모)
- [세 가지 커맨드](#세-가지-커맨드)
- [아키텍처](#아키텍처)
- [Non-trivial 한 설계 결정](#non-trivial-한-설계-결정)
- [비용 및 성능](#비용-및-성능)
- [검증](#검증)
- [3-layer stack](#3-layer-stack)
- [Case study: ghost trap](#case-study-ghost-trap)
- [상태](#상태)
- [로드맵](#로드맵)
- [기여](#기여)
- [인용](#인용)
- [라이선스](#라이선스)
- [Colophon](#colophon)

---

## 이게 왜 필요한가

웬만큼 큰 변경은 다 똑같이 시작합니다. 스펙 몇 문단 쓰고, 뭐가 잘못될지 서너 개 짐작하고, PR 열고, 그러고 나서 반나절 태우면서 "리스크" 중 하나는 애초에 없었고 생각도 못 했던 게 load-bearing 이었다는 걸 발견합니다. 코드 리뷰는 diff *위에* 있는 걸 잡고, 테스트는 본인이 테스트 해야겠다고 생각한 걸 잡습니다. 어느 쪽도 작성자가 이미 plan 에 구워넣은 실수 범주는 못 잡습니다.

**Antemortem** 은 첫 키 입력 *전에* 돌리는 정찰입니다. 본인의 trap 을 종이에 enumerate 하고, plan 과 관련 파일을 LLM 에 넘기면, 각 trap 에 대해 다음 중 정확히 하나를 받습니다:

| 라벨 | 의미 | 모델이 인용해야 할 것 |
|---|---|---|
| `REAL` | 코드가 리스크를 확인함. 완화 없이는 변경이 깨지거나 regresses. | 실패를 유발하는 코드의 `file:line`. |
| `GHOST` | 코드가 리스크를 반박함. 우려한 동작이 일어나지 않거나 기존 완화가 이미 처리함. | 가설을 반박하는 `file:line`. |
| `NEW` | 사용자 리스트에 없던, 모델이 surface 한 리스크. | 해당 리스크를 드러내는 `file:line`. |
| `UNRESOLVED` | 제공된 파일에 어느 쪽 증거도 없음. 정직한 결과이지 실패 아님. | `null` (단, 설명 필수). |

두 가드레일이 *"LLM 에게 내 plan 리뷰해줘"* 로 붕괴하지 않게 막습니다:

1. **모델이 코드를 보기 전에 본인이 trap 을 enumerate 합니다.** 모델 framing 에 anchoring 되는 것을 방지.
2. **UNRESOLVED 가 아닌 모든 classification 은 `file:line` 인용을 담아야 합니다.** API 호출의 Pydantic 스키마 필드로 enforced 되고, 그 다음 `lint` 커맨드가 disk 에서 재검증합니다. 할루시네이트된 line number 는 build 를 fail 시킵니다.

Discipline 자체는 [`hibou04-ops/Antemortem`](https://github.com/hibou04-ops/Antemortem) 에 문서화돼 있습니다. **이 repo 는 그것을 실행하는 도구입니다.**

---

## 30초 데모

```bash
$ antemortem init auth-refactor
Created antemortem/auth-refactor.md (basic template)

# (spec, traps, files 목록 작성...)

$ antemortem run antemortem/auth-refactor.md --repo .
Reading 4 file(s) from . ...
Calling Claude (this can take 30-90s for multi-file recon) ...
Classified 5 traps (2 GHOST, 2 REAL, 1 UNRESOLVED); surfaced 1 new trap(s)
Artifact: antemortem/auth-refactor.json
Tokens: 231 input (+4812 cached read, +0 cached write), 1847 output

$ antemortem lint antemortem/auth-refactor.md --repo .
PASS - auth-refactor.md validates clean (schema + classifications)
```

마지막 `lint` 한 줄이 핵심입니다. 모든 인용이 파싱됐고, 모든 `file:line` 이 `--repo` 안에 실제로 존재함을 확인했고, 모든 range 가 파일 line count 내에 있는지 체크됐습니다. 할루시네이션이 spec 까지 도달하지 못했습니다.

---

## 세 가지 커맨드

### `antemortem init <name>`

공식 템플릿으로부터 문서를 스캐폴드합니다. YAML frontmatter (name, date, scope, reversibility, status, template) + 7개 섹션 본문. `--enhanced` 는 더 풍부한 템플릿으로 교체: calibration 차원 (evidence strength, blast radius, reversibility), 세분화된 classification subtype (REAL-structural, GHOST-mitigated, NEW-spec-gap, …), 모든 REAL/NEW finding 에 대한 명시적 skeptic pass, decision-first output 구조.

```bash
antemortem init my-feature                  # basic
antemortem init prod-migration --enhanced   # 고-stakes 변경용
```

템플릿은 [Antemortem](https://github.com/hibou04-ops/Antemortem) 에서 MIT 로 vendoring 됩니다.

### `antemortem run <doc>`

문서를 parse 하고, spec + traps 테이블 + 나열된 파일 목록을 추출하고, `--repo` 에서 파일 내용을 load 하고, frozen system prompt 와 함께 Anthropic API 를 호출하고, classifications 를 문서 옆 JSON audit artifact 에 쓰기 (`<doc>.json`).

구체적 설계:

| 관심사 | 선택 | 이유 |
|---|---|---|
| 모델 | 단일 Anthropic Claude 버전 코드에 pin | Classification + multi-file chain tracing 은 intelligence-sensitive. 모델 fallback 없음 — prompt contract 안정, 실행 간 동작 재현 가능. |
| 추론 | Adaptive thinking 활성화, `effort: high` | 모델이 제공하는 sampling 손잡이 (temperature / top_p / top_k) 는 pinned 버전에서 제거됨; prompting 이 대체. `high` effort 는 intelligence-sensitive 업무에 대한 벤더 권장 최소값. |
| 출력 형식 | `messages.parse(output_format=AntemortemOutput)` | SDK 경계에서 Pydantic 스키마 enforcement. 잘못 된 응답은 CLI 가 보기 전 `ValidationError` 로 raise. hot path 의 hand-written JSON parsing 없음. |
| 캐싱 | system prompt 에 `cache_control={"type": "ephemeral"}` | System prompt 는 pinned 모델의 cacheable-prefix 최소값을 넘도록 설계됨, 5분 동일 window 내 반복 실행이 base input 비용의 ~0.1× 로 cache hit. CLI 는 매 call 에 `cache_read_input_tokens` 표시 — silent invalidator 가 loud fail 하게. |
| 파일 로딩 | `--repo` root, path-traversal 거부, UTF-8 + replace fallback | `../../etc/passwd` 로 나열된 파일은 warning 과 함께 skip. |

Markdown 문서 자체는 **수정되지 않습니다** — JSON artifact 가 machine-readable output 입니다. `lint` 가 artifact 를 disk 대조 검증합니다. 이 분리는 parsing bug 가 markdown 을 손상시키는 것을 막습니다.

### `antemortem lint <doc>`

CI 에 composable 한 두 단계 검증:

1. **Pre-run (schema)**: frontmatter parse, spec 섹션 텍스트 존재, 최소 하나의 trap enumerate, Recon protocol 아래 최소 하나의 파일. 모든 문서에 적용.
2. **Post-run (citations)**: 문서 옆 `<doc>.json` 존재 시 — 모든 input trap 에 classification, 모든 classification 에 유효한 `path:line` 또는 `path:line-line` 인용, 모든 인용 파일이 `--repo` 에 존재, 모든 line range 가 해당 파일의 bounds 내.

통과 시 exit `0`, 실패 시 `1`, 모든 violation 을 한 줄씩 출력. CI 게이트로: *"그 PR 의 antemortem 이 lint clean 하지 않으면 merge 불가."*

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
│  api.py -> client.messages.parse()                           │
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
│  citations.py -> 모든 path:line 을 disk 에서 검증            │
│  exit 0 = classifications 신뢰 가능                          │
│  exit 1 = 뭔가 fabricated 이거나 out of date                 │
└──────────────────────────────────────────────────────────────┘
```

모든 모듈이 단일 책임을 가짐; 파이프라인은 네트워크 없이 end-to-end 테스트 가능. `AntemortemDocument`, `Classification`, `NewTrap`, `AntemortemOutput` 이 데이터 계약 — 같은 타입이 `run` 에서 `lint` 까지 흐르므로 한쪽의 drift 가 다른 쪽에서 잡힘.

---

## Non-trivial 한 설계 결정

**단일 모델 pin, fallback 없음.** v0.2 에서 다중 모델 "지원" 은 vaporware 입니다. System prompt, 스키마, effort level, adaptive thinking 의 기대 동작 — 모두 모델-특정 계약입니다. 다른 벤더 모델을 drop-in 하려면 이 모든 걸 re-tune 해야 합니다. Prompt 가 안정화되면 v0.3 에서 모델 selector 추가 가능; 그때까지는 pin 이 정직합니다.

**Citation 은 `lint` 가 disk 에서 검증, 신뢰하지 않음.** Structured-output API 는 refusal 하에서 schema conformance 를 깰 수 있고, 잘 동작하는 모델도 긴 파일에서 가끔 line 수를 miscount 합니다. *유일한* 방어는 소스에 대한 재검증입니다. 그래서 `lint` 는 flag 가 아니라 first-class 커맨드입니다.

**JSON artifact 가 출력, markdown 이 입력.** 모델이 markdown 을 in-place 로 편집할 수도 있습니다 — 어떤 도구는 그렇게 합니다. 우리는 안 합니다, 세 가지 이유로: (1) markdown 은 당신 것이지 모델 것이 아닙니다; (2) 어느 방향이든 parse bug 가 수 시간의 작업을 corrupt 할 수 있습니다; (3) machine-readable JSON 은 downstream tooling (CI 게이트, 대시보드, diff 뷰어) 와 깔끔하게 compose 됩니다. Markdown 은 human artifact 로 유지.

**상당한 크기의 system prompt, 의도적.** Pinned 모델은 cacheable-prefix 최소값을 넘는 prefix 를 ~0.1× read 비용에 cache 합니다. 더 짧으면 cache 안 됨; 더 길면 enforce 하는 discipline 으로부터 drift. 모든 substantive 바이트가 load-bearing: role framing, input format, 네 라벨의 정확한 정의, good/bad 예시가 있는 citation rule, anti-pattern 리스트, scope 경계, 네 개의 few-shot 예시. [전체 prompt](src/antemortem/prompts.py) 는 prompt-cache-aware 설계 사례로 읽어볼 만합니다.

**Pydantic v2 스키마가 데이터 계약, dict-모양 comment 아님.** `Classification`, `NewTrap`, `AntemortemOutput`, `Frontmatter`, `AntemortemDocument` 모두 end-to-end 흐름: SDK 가 API 경계에서 검증, `run` 이 검증된 JSON 을 쓰고, `lint` 가 load 시 검증. Malformed classification 은 disk 에 절대 쓰이지 않음.

**Windows path 정규화는 cache-invariant, cosmetic 아님.** `src\foo.py` 와 `src/foo.py` 는 disk 에서 같지만 API payload 에서는 다른 바이트 — prompt caching 을 깹니다. content 가 build 되기 전 모든 path 는 forward slash 로 정규화. `api.py:_build_user_content` 참조.

**`run` 은 `ANTHROPIC_API_KEY` 없을 때 exit 2, 1 아님.** Exit code 는 CI 시스템과의 계약: `1` = content 문제 (사용자가 고쳐야), `2` = 환경 문제 (operator 가 고쳐야). 섞이면 CI triage 어려워집니다.

**Scope 경계는 enforced, 제안 아님.** System prompt 는 명시적으로 말합니다 *"You classify what is in the provided files. You do not: speculate about files not shown, comment on architecture beyond the spec's scope, recommend the user adopt a different design, evaluate whether the change is a good idea."* 사용자가 위 중 하나를 요청하면 모델은 `spec_mutations` 에 "Out of antemortem scope" 로 기록하고 진행하도록 지시받습니다. 이 도구는 한 가지만 합니다.

---

## 비용 및 성능

현재 Anthropic frontier-model 가격 기준 run-당 비용 (전형적 워크로드 추정):

| 시나리오 | 캐시 동작 | 추정 비용 |
|---|---|---|
| 하루 첫 실행 | System prompt 가 cache 에 write (write premium) | ~\$0.15–0.20 |
| 5분 내 동일 prompt 반복 실행 | System prompt cache read (~0.1×) | ~\$0.10–0.12 |
| 활발한 개발 중 100 회 반복 | Write + read 혼합 | \$10–20 |

실제 비용은 모델 tier 와 repository 크기에 따라 변동. 매 `run` 이 토큰 breakdown — `input (+cache_read, +cache_write) output` — 을 출력하므로 매 호출에서 cache 가 engage (또는 silently fail) 하는지 볼 수 있습니다. prompt 가 동일한데도 연속 실행에서 `cache_read_input_tokens` 가 0 이면, prompt 빌드 파이프라인 어딘가에 silent invalidator 가 있다는 뜻 — CLI 가 명시적으로 경고를 출력합니다. [rationale](src/antemortem/api.py) 는 `api.py` 에.

기본 `--max-tokens` 는 16000, 전형적 output 은 1–4k. 큰 surface 의 드문 deep recon 을 위해 128000 까지 올릴 수 있음.

---

## 검증

**68 tests, 0 네트워크 호출.** Anthropic client 는 `api.py` 의 `Protocol` 인터페이스로 받으므로, 모든 API 테스트는 `SimpleNamespace` 나 `MagicMock` 으로 응답을 모킹합니다. 두 가지가 보장됨: API 크레딧 소비 없는 결정론적 CI, 그리고 실제 서버와 협상 없이 request payload 의 *정확한* shape (model, thinking config, cache_control 배치, 정렬된 파일 순서) 을 assert 할 수 있는 테스트-시점 자유도.

테스트 surface:

| 모듈 | 커버리지 |
|---|---|
| `schema.py` | 9 tests — 필수 필드, label enum, UNRESOLVED 의 nullable citation, NewTrap id pattern, JSON roundtrip. |
| `citations.py` | 13 tests — range 파싱, Windows backslash 정규화, 빈 문자열 / prose / zero-line / reversed-range 거부, path traversal 포함 disk 검증. |
| `parser.py` | 12 tests — frontmatter 검증, 섹션 추출, recon-vs-pre-recon 구분, placeholder-row 필터링과 trap 테이블 파싱. |
| `lint.py` | 11 tests — 두 단계 (schema-only 와 artifact), 모든 violation 경로, exit code. |
| `api.py` | 5 tests — payload shape, 파일 정렬 결정성, refusal branch, parsed-output 계약, dict-fallback coercion. |
| `run.py` | 7 tests — 모킹된 client 로 전체 흐름, 에러 경로, 경고, JSON-summary env var. |
| `init.py` | 6 tests — basic + enhanced 템플릿, `--force`, path traversal 거부, ISO 날짜 frontmatter. |
| `cli.py` | 5 tests — `--help`, `--version`, no-args-prints-help. |

`uv run pytest -q` 로 실행. 전형적 wall time: 0.2s.

---

## 3-layer stack

이 CLI 는 고립돼 존재하지 않습니다. Layered discipline 의 3번째 tier 입니다:

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

- **[omega-lock](https://github.com/hibou04-ops/omega-lock)** 은 Antemortem discipline 이 *처음 실제로 practice 된* Python calibration framework. `omega_lock.audit` 서브모듈이 15분짜리 antemortem recon 을 사용해 빌드됐고, 그 recon 이 구현 전에 ghost trap 하나를 잡고 세 개의 리스크를 downgrade 했습니다.
- **[Antemortem](https://github.com/hibou04-ops/Antemortem)** 은 그 빌드에서 결정화된 methodology: 7-step 프로토콜, basic 과 enhanced 템플릿, 첫 case study. Docs-only.
- **antemortem-cli** (이 repo) 는 마찰을 제거하는 도구: `init` 으로 스캐폴드, `run` 으로 classify, `lint` 로 verify. 세 커맨드, 하나의 데이터 계약, disk-verified citation.

Layering 은 정확성에 중요합니다: methodology 는 CLI 빌드 *전에* 실제 shipped artifact 로 validated 됐으므로, tool 은 이미 작동하는 걸로 알려진 프로토콜을 automate 하는 것이지 도구와 나란히 발명된 프로토콜이 아닙니다.

---

## Case study: ghost trap

`omega_lock.audit` 서브모듈이 빌드되기 전, 리스트에 7개 리스크가 있었습니다. 모델이 매 classification 에 `file:line` 을 인용하는 15분 antemortem recon 이 produce 한 결과:

- **Ghost 하나.** Trap #1 은 *"WalkForward 가 내부에서 fold 하므로 audit decorator 가 평가 비용을 이중으로 센다."* 모델이 `src/omega_lock/walk_forward.py:82` 를 인용 — `return self._evaluate(params)` 한 줄, 주변 loop 없음. 두려워한 fold 가 존재하지 않았음. ≈0.5 engineer-day 절약.
- **리스크 세 개 하향.** JSON serialization, 큰 candidate set 에서 메모리 blow-up, iterative-round bookkeeping 모두 codebase 에 기존 완화 존재. 각각 P(issue) 30–40% 에서 10–15% 로 하락.
- **새 요구사항 하나.** 모델이 `Target` 이 같은 흐름에서 searcher, evaluator, renderer 세 역할로 사용됨을 눈치채고 구현 전에 spec 에 `target_role` 필드를 권장. 수용; 구현 중간에 surface 했을 모호성 회피.

Recon 후 `P(full spec ships on time)` 가 55–65% 에서 70–78% 로 이동. 구현 1 engineer-day 소요. 신규 20개 테스트가 first run 에 통과.

전체 writeup 은 Antemortem repo 의 [`examples/omega-lock-audit.md`](https://github.com/hibou04-ops/Antemortem/blob/main/examples/omega-lock-audit.md), recon 이 놓친 것에 대한 정직한 post-implementation 노트 포함 (Windows cp949 em-dash 터미널 인코딩 이슈가 런타임에 surface — antemortem 은 플랫폼 인코딩 이슈를 못 잡음, [methodology.md § Limits](https://github.com/hibou04-ops/Antemortem/blob/main/docs/methodology.md#limits) 에 이제 나열됨).

---

## 상태

v0.2.0 은 **alpha**. CLI 계약 (세 커맨드, 그들의 flag, exit code) 은 stable. Prompt 는 다양한 실제 repo 에서 classification 품질 데이터가 축적되면서 iterate — v0.2.x bump 는 prompt 수정 용도로 사용, CHANGELOG 의 *"Prompt revisions"* 섹션에 추적. JSON artifact 스키마는 v0.2.x 내에서 stable; 스키마 breaking change 는 v0.3 cut.

Semver 는 v1.0 부터 엄격 적용.

전체 changelog: [CHANGELOG.md](CHANGELOG.md).

---

## 로드맵

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

**명시적 out of scope** (v0.2 이후 포함): 웹 대시보드, DB-backed 히스토리, 멀티유저 tenancy, proprietary hosting. antemortem 은 로컬 개발자 도구; 로컬에 유지.

---

## 기여

Case study 는 [Antemortem methodology repo](https://github.com/hibou04-ops/Antemortem) 의 `examples/` 아래 PR 로 — 가장 가치 있고 가장 찾기 어려운 기여입니다. Bar: *"모든 classification 이 `file:line` 인용, post-implementation 노트 존재, recon 이 놓친 것에 정직할 것."*

도구 레벨 기여 (새 CLI flag, 스키마 필드, prompt 수정) 는 이 repo 의 `main` 대상 PR. 가능하면 해당 변경에 대한 antemortem 문서 첨부 — 도구는 자기 자신의 개발에 dogfood 됩니다.

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
