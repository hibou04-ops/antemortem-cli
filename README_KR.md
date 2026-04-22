# antemortem-cli (한국어)

> **처음이신가요?** 먼저 보세요: [EASY_README_KR.md](EASY_README_KR.md) (한국어) · [EASY_README.md](EASY_README.md) (English). 아래 본 문서가 어렵게 느껴지는 분들을 위한 압축된 쉬운 소개.

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![PyPI](https://img.shields.io/badge/pypi-0.4.0-blue.svg)](https://pypi.org/project/antemortem/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](#상태--로드맵)
[![Tests](https://img.shields.io/badge/tests-111%20passing-brightgreen.svg)](tests/)
[![Providers](https://img.shields.io/badge/providers-anthropic%20%7C%20openai%20%7C%20openai--compatible-informational.svg)](#provider-지원)
[![Methodology](https://img.shields.io/badge/methodology-Antemortem-blueviolet.svg)](https://github.com/hibou04-ops/Antemortem)

> **당신의 다음 feature 에는 7개의 리스크가 있습니다. 그중 5개는 상상 속에만 존재합니다. 2개는 아직 이름조차 붙지 않았습니다.**
>
> Antemortem 은 어느 것이 어느 것인지 — 코드에서, 15분 안에, lint 가 검증할 수 있는 file-and-line 인용과 함께 — 알려줍니다. diff 를 쓰기 전에. 어떤 frontier LLM 에서든 작동: Anthropic, OpenAI, 또는 OpenAI-호환 endpoint (Azure OpenAI, Groq, Together.ai, OpenRouter, 로컬 Ollama).

```bash
pip install antemortem
```

English README: [README.md](README.md)

---

## 목차

- [이 도구가 해결하는 failure mode](#이-도구가-해결하는-failure-mode)
- [Worked example: 실제 ghost trap](#worked-example-실제-ghost-trap)
- [세 가지 커맨드](#세-가지-커맨드)
- [Provider 지원](#provider-지원)
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

문서를 parse, spec + traps 테이블 + 나열된 파일 목록 추출, `--repo` 에서 파일 내용 load, frozen system prompt 와 함께 설정된 provider 호출, classifications 를 문서 옆 JSON audit artifact 에 쓰기 (`<doc>.json`).

```bash
# Anthropic (기본)
antemortem run antemortem/my-feature.md --repo .

# OpenAI
antemortem run antemortem/my-feature.md --repo . --provider openai

# OpenAI-호환 endpoint (로컬 Ollama, Azure, Groq 등)
antemortem run antemortem/my-feature.md --repo . \
  --provider openai \
  --model llama3.1:70b \
  --base-url http://localhost:11434/v1

# 선택적 2nd-pass critic (API 비용 ~2배, 고-stakes 전용)
antemortem run antemortem/my-feature.md --repo . --critic
```

**선택적 second pass — `--critic`.** Critic 은 REAL 및 NEW finding 을 같은 evidence 에 대조해 재검토하고 `CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE` 중 정확히 하나를 반환. 전용 ~1.5k-token critic prompt 는 명시적으로 비대칭: critic 은 오직 downgrade 만 가능. `WEAKENED` → `UNRESOLVED`; `CONTRADICTED` → counterevidence 에 따라 `GHOST` 또는 `UNRESOLVED`; `DUPLICATE` → drop; `CONFIRMED` → 그대로. 비대칭이 load-bearing. Promote 할 수 있는 critic 은 자신의 quality signal 을 오염시키고, downgrade 만 하는 critic 은 추가 한 번의 호출 비용으로 순수 quality multiplier 가 됨. 기본 꺼짐. False REAL 이 비싼 변경에서 켤 것.

**4-level 결정 게이트 (기본 on, `--no-decision` 으로 skip).** 매 run 이 정확히 다음 중 하나를 emit:

| 결정 | 발동 조건 |
|---|---|
| `SAFE_TO_PROCEED` | Critic 조정 후 REAL finding 없음. |
| `PROCEED_WITH_GUARDS` | REAL finding 존재; 전부 `remediation` 텍스트 있음. |
| `NEEDS_MORE_EVIDENCE` | Unresolved 비율이 높거나 gate 할 citation 없음. |
| `DO_NOT_PROCEED` | `severity: high` 인 REAL finding 이 최소 하나 존재하고 `remediation` 없음. |

게이트는 결정론적 — 같은 artifact in, 같은 decision out — 따라서 CI 시스템은 prose 해석 없이 특정 level 을 whitelist/blacklist 가능. `run.py` 가 decision 줄을 색상 코딩하고 한 문장짜리 rationale 출력; `ANTEMORTEM_JSON_SUMMARY=1` 이 usage 카운터와 함께 decision 을 노출.

관심사별 설계 — 인터페이스는 vendor-neutral 유지, adapter 내부는 vendor-native:

| 관심사 | 인터페이스 (안정) | Provider 별 실현 |
|---|---|---|
| **출력 형식** | `LLMProvider.structured_complete(output_schema=AntemortemOutput)` 가 Pydantic-validated 객체 반환. | Anthropic: `messages.parse(output_format=...)`. OpenAI: `beta.chat.completions.parse(response_format=...)`. 둘 다 서버 측 스키마 enforce; 클라이언트 측 regex fallback 없음. |
| **캐싱** | CLI 가 매 call 에 `input / cache_read / cache_write / output` 보고. | Anthropic: system 블록에 명시적 `cache_control={"type": "ephemeral"}`. OpenAI: 자동 prompt caching (provider threshold 넘으면 marker 없이 서버 측 cache). |
| **추론 / thinking** | Adapter-specific. Anthropic adapter 는 기본으로 adaptive thinking + `effort: high`. OpenAI adapter 는 모델의 네이티브 동작 passthrough. | Provider 별 설정 가능. OpenAI `o1` / `o3`-class 모델용 first-class reasoning-effort passthrough 는 v0.5 트랙. |
| **Sampling 손잡이** | 인터페이스에서 제외. | Discipline 은 temperature / top_p 에 의존 안 함. Adapter 들이 이를 send 안 함. |
| **Refusal 처리** | Actionable 메시지와 함께 `ProviderError` raise. | Anthropic: `stop_reason == "refusal"`. OpenAI: `finish_reason == "content_filter"`. |
| **파일 로딩** | `--repo` root, path-traversal 거부, UTF-8 + replace fallback. | Provider 간 동일; discipline 자체의 보장. |

Markdown 문서 자체는 **수정되지 않습니다**. JSON artifact 가 machine-readable output. `lint` 가 artifact 를 disk 대조 검증. 이 분리는 parsing bug 가 markdown 을 손상시키는 것을 막습니다.

### `antemortem lint <doc>`

CI 에 composable 한 두 단계 검증:

1. **Pre-run (schema)**: frontmatter parse, spec 섹션 텍스트 존재, 최소 하나의 trap enumerate, Recon protocol 아래 최소 하나의 파일. 모든 문서에 적용.
2. **Post-run (citations)**: 문서 옆 `<doc>.json` 존재 시 — 모든 input trap 에 classification, 모든 classification 에 유효한 `path:line` 또는 `path:line-line` 인용, 모든 인용 파일이 `--repo` 에 존재, 모든 line range 가 해당 파일의 bounds 내.

통과 시 exit `0`, 실패 시 `1`, 모든 violation 을 한 줄씩 출력. CI 게이트로: *"그 PR 의 antemortem 이 lint clean 하지 않으면 merge 불가."*

---

## Provider 지원

`antemortem-cli` 는 `LLMProvider` Protocol 을 통해 LLM 과 통신합니다. Discipline 은 vendor-neutral; 오직 하나의 seam 만 pluggable. 각 adapter 는 vendor 의 가장 강한 네이티브 schema-enforcement 메커니즘 사용 — 파이프라인 어디에도 클라이언트 측 JSON regex-parsing 없음.

| Provider | 플래그 | 기본 모델 | Env var | Native structured output | 참고 |
|---|---|---|---|---|---|
| Anthropic | `--provider anthropic` (기본) | `claude-opus-4-7` | `ANTHROPIC_API_KEY` | 명시적 `cache_control` 을 동반한 `messages.parse` | Adaptive thinking + `effort: high` 기본 활성화. |
| OpenAI | `--provider openai` | `gpt-4o` | `OPENAI_API_KEY` | `response_format` 을 동반한 `beta.chat.completions.parse` | System prompt 가 provider threshold 이상이면 자동 prompt caching. |
| OpenAI-호환 | `--provider openai --base-url <url>` | 사용자 지정 `--model` | `OPENAI_API_KEY` (로컬 미인증 endpoint 는 임의 문자열) | OpenAI 와 같은 경로 | Azure OpenAI, Groq, Together.ai, OpenRouter, 로컬 Ollama (`http://localhost:11434/v1`) 커버. |

**확장:** 새 provider 구현은 한 모듈. `LLMProvider` Protocol 만족 (한 메서드: `structured_complete`), `providers/factory.py` 에 등록, 이 테이블에 행 추가. CLI surface 와 data contract 는 변경 불필요.

**`LLMProvider` Protocol** (`src/antemortem/providers/base.py`):

```python
class LLMProvider(Protocol):
    name: str
    model: str
    def structured_complete(
        self,
        *,
        system_prompt: str,
        user_content: str,
        output_schema: type[T],
        max_tokens: int = 16000,
    ) -> tuple[T, dict[str, int]]: ...
```

한 메서드. SDK 누출 없음. System prompt 는 구성상 provider-neutral — 같은 프롬프트 텍스트가 모든 vendor 에서 작동.

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

# ↓ run.py → provider.structured_complete(output_schema=AntemortemOutput)
AntemortemOutput(
    classifications=[
        Classification(
            id="t1",
            label="REAL",
            citation="src/auth/middleware.py:45-52",
            note="Refresh 경로 (48번째 줄) 가 새 토큰을 발급하지만 기존 세션 쿠키는 건드리지 않음.",
            severity="high",
            confidence=0.82,
            remediation="Refresh 핸들러에서, 새 토큰 발급 전 만료된 Max-Age 를 가진 Set-Cookie 로 기존 세션 쿠키를 명시적으로 clear.",
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
            severity="medium",
        ),
    ],
    spec_mutations=[
        "추가: 토큰 rotation 시, 기존 세션 쿠키의 명시적 무효화.",
        "추가: Rotation 시퀀스에 CDN 캐시 무효화 단계.",
    ],
    # ↓ critic.py 가 채움, --critic 전달 시에만 (v0.4)
    critic_results=[
        CriticResult(
            finding_id="t1",
            status="CONFIRMED",
            issues=[],
            counterevidence=[],
            recommended_label=None,
        ),
    ],
    # ↓ decision.py 가 채움, --no-decision 으로 억제 (v0.4)
    decision="PROCEED_WITH_GUARDS",
    decision_rationale="구체적 remediation 을 가진 REAL finding 1개 (t1); mitigation 없는 high-severity finding 없음.",
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
│  api.py → provider.structured_complete()                     │
│    ┌─ AnthropicProvider ─ messages.parse(output_format=...)  │
│    │                      thinking: adaptive, effort: high   │
│    │                      cache_control: ephemeral           │
│    ├─ OpenAIProvider    ─ beta.chat.completions.parse()      │
│    │                      response_format=AntemortemOutput   │
│    │                      (자동 prompt caching)               │
│    └─ <custom>          ─ Protocol 만족하면 끝                │
└────────────────┬─────────────────────────────────────────────┘
                 │  Vendor-native schema enforcement
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  AntemortemOutput  (first pass)                              │
│    classifications[]  (id, label, citation, note,            │
│                        severity?, confidence?, remediation?) │
│    new_traps[]        (hypothesis, citation, note, ...)      │
│    spec_mutations[]   (spec 에 대한 자유 형식 edit)           │
└────────────────┬─────────────────────────────────────────────┘
                 │  critic.py  (--critic 으로 opt-in)           │
                 │    두 번째 provider 호출, 비대칭:             │
                 │    CONFIRMED / WEAKENED / CONTRADICTED /     │
                 │    DUPLICATE — downgrade 만, 절대 promote    │
                 │    안 함.                                     │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  AntemortemOutput  +  critic_results[]                       │
└────────────────┬─────────────────────────────────────────────┘
                 │  decision.py  (기본 on, --no-decision)       │
                 │    severity + remediation + critic 결과      │
                 │    위의 결정론적 4-level 게이트.              │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  AntemortemOutput  +  decision  +  decision_rationale        │
│    decision ∈ { SAFE_TO_PROCEED, PROCEED_WITH_GUARDS,        │
│                 NEEDS_MORE_EVIDENCE, DO_NOT_PROCEED }        │
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

모든 모듈이 단일 책임; 파이프라인은 네트워크 없이 end-to-end 테스트 가능. `AntemortemDocument`, `Classification`, `NewTrap`, `CriticResult`, `AntemortemOutput` 이 데이터 계약 — 같은 타입이 `run` 에서 `critic`, `decision` 을 거쳐 `lint` 까지 흐르므로 한쪽의 drift 가 다른 쪽들에서 잡힘.

---

## Non-trivial 한 설계 결정

**Vendor-neutral 인터페이스, vendor-native adapter.** `LLMProvider` Protocol 은 한 메서드, 그리고 vendor-특정 knob 없음. 각 adapter 는 vendor 의 가장 강한 네이티브 schema-enforcement 경로 사용 — Anthropic 은 `messages.parse`, OpenAI 는 `beta.chat.completions.parse` — 그리고 vendor 의 네이티브 caching semantics. Discipline (Pydantic enforcement, disk-verified citations, stable exit codes) 은 provider 간 동일. 새 provider 추가는 한 모듈이고 CLI 나 data contract 를 건드리지 않음.

**System prompt 는 provider-neutral 하게 작성.** `src/antemortem/prompts.py` 의 ~5k 토큰 `SYSTEM_PROMPT` 는 특정 vendor, 모델, API surface 를 참조하지 않음. LLM 이 만족해야 할 항목 (네 개의 정확한 라벨 정의, good/bad 예시가 있는 citation rule, scope 경계, few-shot JSON 예시) 으로 discipline 을 정의. Provider 교체 시 re-tuning 불필요.

**Citation 은 `lint` 가 disk 에서 검증, 신뢰하지 않음.** Structured-output API 는 refusal 하에서 schema conformance 를 깰 수 있고, 잘 동작하는 모델도 긴 파일에서 가끔 line 을 miscount. 모델의 self-report citation 을 신뢰하는 것은 테스트된 PR 이 버그 없다고 믿는 것과 같은 실수. *유일한* 방어는 소스 대조 재검증. `lint` 는 `--strict` flag 가 아니라 first-class 커맨드 — CI 게이트가 ceremony 없이 돌릴 수 있어야 하므로.

**JSON artifact 가 출력, markdown 이 입력.** 모델이 markdown 을 in-place 로 편집할 수 있음 — 어떤 도구는 그렇게 함. 우리는 안 함, 세 가지 이유로: (1) markdown 은 당신 것이지 모델 것 아님; (2) 어느 방향이든 parse bug 가 수 시간의 작업을 corrupt 할 수 있음; (3) machine-readable JSON 은 downstream tooling (CI 게이트, 대시보드, diff 뷰어) 과 깔끔하게 compose. Markdown 은 human artifact 로 유지.

**~5k 토큰 system prompt, 의도적.** Anthropic 과 OpenAI 모두 각자의 threshold 를 넘는 prefix 를 cache; prompt 는 양쪽 모두 넉넉히 넘도록 sized. 더 짧으면 신뢰할 만하게 cache 안 됨; 더 길면 enforce 하는 discipline 으로부터 drift. 모든 substantive 바이트가 load-bearing: role framing, input format, 네 라벨의 정확한 정의, good/bad 예시가 있는 citation rule, anti-pattern 리스트, scope 경계, 네 개의 few-shot JSON 예시. [전체 prompt](src/antemortem/prompts.py) 는 prompt-cache-aware 설계 사례.

**Pydantic v2 스키마가 데이터 계약, dict-모양 comment 아님.** `Classification`, `NewTrap`, `AntemortemOutput`, `Frontmatter`, `AntemortemDocument` 모두 end-to-end 흐름: SDK 가 API 경계에서 검증, `run` 이 검증된 JSON 을 쓰고, `lint` 가 load 시 검증. Malformed classification 은 disk 에 절대 쓰이지 않음 — 즉, main 에 merge 되지 않음.

**Windows path 정규화는 cache-invariant, cosmetic 아님.** `src\foo.py` 와 `src/foo.py` 는 disk 에서 같지만 API payload 에서는 다른 바이트 — cache key 는 byte-exact. content 가 build 되기 전 모든 path 는 forward slash 로 정규화. `api.py:_build_user_content` 참조. 3줄짜리 수정이 놓치면 100 run 당 ~\$15 silently 낭비.

**`run` 은 환경 이슈에 exit 2, content 이슈에 exit 1.** Exit code 는 CI 시스템과의 계약: `1` = 사용자가 antemortem 에서 고칠 수 있는 content 문제 (trap 빠짐, 파일 읽기 불가, provider refusal); `2` = operator 가 고치는 환경 문제 (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` 빠짐, 알 수 없는 `--provider`, SDK 미설치). 분리가 명시적인 건 섞이면 CI triage 어려워지기 때문.

**Scope 경계는 prompt 에서 enforced, 제안 아님.** System prompt 는 명시적으로 말함: *"You classify what is in the provided files. You do not: speculate about files not shown, comment on architecture beyond the spec's scope, recommend the user adopt a different design, evaluate whether the change is a good idea."* 사용자가 위 중 하나를 요청하면 모델은 `spec_mutations` 에 "Out of antemortem scope" 로 기록하고 진행하도록 지시받음. 이 도구는 한 가지만 함.

**Critic pass 는 비대칭 — downgrade 만.** `--critic` 이 두 번째 provider 호출을 추가. 해당 prompt (~1.5k 토큰, classifier prompt 와 격리) 는 모델에게 모든 REAL 및 NEW finding 을 adversarially 재검토하고 `CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE` 중 하나를 반환하도록 지시. 이 status 들을 소비하는 정책은 의도적으로 한 방향: finding 은 REAL / NEW *에서* UNRESOLVED / GHOST / drop *으로* 움직일 수 있고 반대 방향은 절대 없음. 대칭적 critic 은 자신의 signal 을 오염시킴 — critic 이 UNRESOLVED 를 REAL 로 promote 할 수 있다면 노이즈 낀 critic 이 finding 을 지어내고 second pass 가 quality multiplier 가 되지 못함. 비대칭이 방어. 비용 모델도 이로써 고정됨: worst case, `--critic` 은 API 지출을 2배; best case, 정밀도를 silently 개선.

**Decision gate 는 opt-out, opt-in 아님.** 기본적으로 매 `run` 이 4-level 결정 (`SAFE_TO_PROCEED` / `PROCEED_WITH_GUARDS` / `NEEDS_MORE_EVIDENCE` / `DO_NOT_PROCEED`) 중 하나를 emit, finding count, `severity`, `remediation` 존재 여부, critic 결과로부터 결정론적으로 선택. `--no-decision` 은 raw artifact 를 원하는 caller 를 위해 존재 — 그러나 CI 는 묻지 않고도 의견을 받아야 함. 게이트의 결정론이 중요: 같은 artifact in, 같은 decision out — LLM 호출 없음, sampling 없음, 따라서 downstream whitelist/blacklist 가 동일 입력에서 stable. 팀은 도구 내부 threshold 를 tweak 하는 게 아니라 특정 level 로 gate 해서 policy 를 override.

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

Run-당 비용은 provider 와 tier 에 따라 다름. Rough envelope:

| Provider + tier | 첫 run (cache write) | Cached 후속 run | 100-run 반복 예산 |
|---|---|---|---|
| Anthropic frontier (Opus-class) | ~\$0.15–0.20 | ~\$0.10–0.12 | \$10–20 |
| Anthropic mid-tier (Sonnet-class) | ~\$0.04–0.08 | ~\$0.03–0.05 | \$3–8 |
| OpenAI frontier (`gpt-4o`) | ~\$0.08–0.15 | ~\$0.05–0.10 | \$5–15 |
| OpenAI mini-tier (`gpt-4o-mini`) | ~\$0.01–0.03 | ~\$0.005–0.015 | \$1–3 |
| Ollama 로컬 (`llama3.1:70b`) | 무료 (컴퓨팅만) | 무료 | 무료 |

매 `run` 이 `input (+cache_read, +cache_write) output` + 해결된 `provider / model` 을 출력 — 매 호출에서 cache 가 engage 하는지 silently fail 하는지 보임. Prompt 가 동일한데도 연속 실행에서 `cache_read_input_tokens` 가 0 이면 prompt 빌드 파이프라인 어딘가에 silent invalidator — CLI 가 명시적으로 경고 출력. (로컬 endpoint 는 설계상 0 cache 토큰 보고; Ollama 대상 실행 시 그 경고 무시.)

기본 `--max-tokens` 는 16000. 전형적 output 은 1–4k. 큰 surface 의 드문 deep recon 을 위해 128000 까지 올릴 수 있음.

---

## 검증

**111 tests, CI 에서 네트워크 호출 0.** 모든 provider (현재 + 미래) 는 `LLMProvider` Protocol 로 받음 — 모든 API 테스트는 `SimpleNamespace` 나 `MagicMock` 으로 client 를 mock. 두 가지 benefit: API 크레딧 소비 없는 결정론적 CI, 그리고 실제 서버와 협상 없이 request payload 의 *정확한* shape (model, thinking config, cache_control 배치, `response_format`, 정렬된 파일 순서) 을 assert 할 수 있는 테스트-시점 자유도.

| 모듈 | 커버리지 |
|---|---|
| `schema.py` | 9 tests — 필수 필드, label enum, UNRESOLVED 의 nullable citation, NewTrap id pattern, JSON roundtrip. |
| `citations.py` | 14 tests — range 파싱, Windows backslash 정규화, 빈 문자열 / prose / zero-line / reversed-range 거부, path traversal 포함 disk 검증. |
| `parser.py` | 11 tests — frontmatter 검증, 섹션 추출, `recon-protocol` vs `pre-recon` 구분, placeholder-row 필터링과 trap 테이블 파싱. |
| `lint.py` | 11 tests — 두 단계 (schema-only 와 artifact), 모든 violation 경로, exit code. |
| `providers/` | 19 tests — factory 가 알 수 없는 이름 거부, 기본값 사용, `--base-url` passthrough; Anthropic adapter 가 예상 kwargs build / refusal raise / dict-output coerce; OpenAI adapter 가 `prompt_tokens_details.cached_tokens` → `cache_read_input_tokens` 매핑 / content_filter raise / missing parsed raise. |
| `api.py` | 5 tests — user-payload shape, Windows path 정규화, provider-delegation 계약, error propagation. |
| `critic.py` | 12 tests — payload 조립 블록 (`<files>`, `<spec>`, `<traps>`, `<first_pass>`), provider-delegation 계약, 네 status 정책 결과 (`CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE`) 가 first-pass artifact 위에 결정론적으로 적용됨. |
| `decision.py` | 13 tests — 4개 결정 결과 전부, edge case: 빈 classifications, REAL-with-remediation vs REAL-without, severity-high gating, critic-downgrade 상호작용, unresolved-only 입력. |
| `run.py` | 8 tests — 모킹된 provider 로 전체 흐름, 에러 경로, 경고, JSON-summary env var, cache-miss 경고 surface, critic pass 위임. |
| `init.py` | 6 tests — basic + enhanced 템플릿, `--force`, path traversal 거부, ISO 날짜 frontmatter. |
| `cli.py` | 3 tests — `--help` 가 세 커맨드 나열, `--version`, no-args-prints-help. (커맨드별 동작은 `run.py` / `lint.py` / `init.py` 에서 커버.) |

`uv run pytest -q` 로 실행. 전형적 wall time: 0.5s 미만.

---

## 3-layer stack

이 CLI 는 point tool 이 아니라 layered discipline 의 3번째 tier:

```
         ┌─────────────────────────────────────────────┐
 Layer 3 │  antemortem-cli  (this repo)                │  "Discipline 을 실행"
         │  0.4.0 — CLI + lint + multi-provider        │
         │          + critic + decision gate           │
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

**그냥 LLM 에게 "내 spec 리뷰해줘" 하면 되지 않나?**

그게 이 도구가 방지하려는 degenerate case. 두 가드레일 없이는 LLM 이 당신이 쓴 것에 기꺼이 동의. 일반적 리스크와 진짜 리스크가 섞인 리스트를 받고, 어느 게 어느 건지 구분할 수 없고, 모델이 주장을 뒷받침하도록 압박이 없음. `file:line` 요구 + `lint` 의 재검증이 "의견" 과 "증거" 의 차이.

**모델 선택이 중요한가요?**

Discipline 은 설계상 vendor-neutral 이지만 모델 능력은 중요. 이 도구는 모델에게 multi-file call chain 추적, 정확한 `file:line` citation 으로 분류, 엄격한 JSON 스키마 준수를 요구. Frontier-tier 모델 (Anthropic Opus-class, OpenAI `gpt-4o` 이상, 또는 유능한 로컬 reasoner) 이 이 bar 통과; 작은 모델은 더 많은 UNRESOLVED 라벨 생성 가능 — 여전히 valid 한 결과이지만 덜 유용. `lint` 가 모델 관계없이 조작된 citation 을 mechanical 로 잡으므로 약한 모델의 최악 케이스는 "low signal" 이지 "wrong signal" 이 아님.

**모델이 line number 를 그냥 지어낼 건데?**

가끔 그럴 것. 그래서 `lint` 가 존재. 모든 citation 이 parsed, 파일이 load, line range 가 실제 파일 bound 와 대조. 할루시네이트된 citation 은 lint fail. 모델은 *"A fabricated line number is strictly worse than UNRESOLVED — UNRESOLVED is honest, fabrication is not"* 라고 지시받고, discipline 이 mechanical 검증으로 이를 backup.

**비공개/private 코드에서 작동하나요?**

네. LLM 은 당신이 주는 걸 읽음; public repo 필요 없음. 유일 제약은 공개 case study 의 citation 은 repo 없이도 readers 가 verify 할 수 있도록 inline context 를 충분히 quote 해야 함.

**IDE 플러그인은? Web UI 는?**

범위 밖, 설계상. CLI 가 CI-gate 도구에 맞는 surface — GitHub Actions, pre-commit hook, 로컬 Makefile 에서 `antemortem lint` 가능. Web UI 는 state + auth 추가; 플러그인은 IDE 확장 API 에 coupling. 둘 다 primary use case (merge-gate) 에 더 나쁨.

**Go / Rust / TypeScript 인데 쓸 수 있나요?**

네. Antemortem 은 언어-agnostic — Python AST 가 아니라 *파일* 을 읽음. CLI 는 Python 패키지지만 target repo 는 아무거나. Case study 는 Python; discipline 은 Rust crate 나 TypeScript monorepo 에서도 같게 작동.

**Cursor / Claude Code / Aider 의 "plan" 모드와 어떻게 다른가요?**

그 도구들은 planning 을 편집 loop 에 통합 — 유용하지만, plan 이 구현과 같은 세션에 있음. Antemortem 은 보존할 *별도 artifact*. 6개월 후 feature 가 당신을 놀라게 했을 때, `antemortem/auth-refactor.md` 를 다시 읽고 어떤 가정이 깨졌는지 볼 수 있음. Ephemeral chat 이 아니라 disciplined paper trail.

**왜 Python 인가요?**

첫 사용자가 omega-lock (Python) 위에 빌드하고 있었기 때문, 그리고 Anthropic 과 OpenAI Python SDK 둘 다 first-class structured-output 경로 (`messages.parse` / `beta.chat.completions.parse`) 가지므로. 이 도구는 100% offline-validatable (`lint` 는 네트워크 필요 없음) 이라 Python 런타임이 hot-path 제약이 아님.

**로컬 모델 사용 가능한가요?**

네 — 어떤 OpenAI-호환 endpoint 든 `--base-url` 로 작동. Ollama 의 호환 레이어 `http://localhost:11434/v1` 가 zero-config 기본:

```bash
antemortem run antemortem/my-feature.md --repo . \
  --provider openai \
  --base-url http://localhost:11434/v1 \
  --model llama3.1:70b
```

Lint discipline (disk-verified citations) 은 변하지 않음. Classification 품질은 로컬 모델의 능력에 의존 — `lint` 가 모델 관계없이 조작을 잡음.

---

## 선행 연구 및 credit

이 도구가 서 있는 두 아이디어:

- **Pre-mortem** — Gary Klein, *"Performing a Project Premortem"*, Harvard Business Review, 2007년 9월. 아이디어의 팀-전략적 버전.
- **Winchester defense** — 원래 quant-finance discipline: *kill criteria 는 run 전에 선언되어야 하고, 이후에 완화될 수 없음*. 여기선 `lint` 가 self-report 에 의존하지 말고 gate 시점에 citation 을 mechanical 로 검증해야 함을 주장하는 데 사용. Parameter-calibration analog 는 omega-lock 의 [`docs/methodology.md § Kill criteria`](https://github.com/hibou04-ops/omega-lock/blob/main/src/omega_lock/kill_criteria.py) 참조.

네이밍은 명시적: *postmortem* (죽음 후) → *antemortem* (죽음 전). Methodology 는 2026년 4월 `omega_lock.audit` 서브모듈 빌드 중 emerge 했고 [hibou04-ops/Antemortem](https://github.com/hibou04-ops/Antemortem) 에 문서화.

---

## 상태 & 로드맵

v0.4.0 은 **alpha**. CLI 계약 (세 커맨드, flag, exit code) 은 stable. JSON artifact 스키마는 v0.4.x 내에서 additive — v0.4 는 `critic_results`, `decision`, `decision_rationale` 와 per-finding optional `confidence` / `remediation` / `severity` 를 도입; 전부 v0.3.x caller 에 non-breaking 이며 v0.3.x artifact 도 그대로 validate. Prompt iteration 은 classifier 와 critic 양쪽에서 계속 — 다양한 실제 repo 에서 classification 품질 데이터가 축적되면서, v0.4.x bump 는 prompt 수정 용도, CHANGELOG 의 *"Prompt revisions"* 섹션에 추적. 스키마 breaking change 는 v0.5 cut.

Semver 는 v1.0 부터 엄격 적용.

**Shipped**
- **v0.2** — 스캐폴드 (`init`), 분류 (`run`, Claude Opus 4.x 대상), lint (schema + disk-verified citation). 토대가 된 세-커맨드 CLI surface.
- **v0.3** — `LLMProvider` Protocol 과 `providers/` 패키지; 각 vendor 의 가장 강한 네이티브 schema-enforcement 경로를 쓰는 Anthropic / OpenAI adapter; `--base-url` 로 임의의 OpenAI-호환 endpoint (Azure, Groq, Together.ai, OpenRouter, 로컬 Ollama).
- **v0.4** — `--critic` 비대칭 second-pass 리뷰 (downgrade 만); 4-level decision gate (`SAFE_TO_PROCEED` / `PROCEED_WITH_GUARDS` / `NEEDS_MORE_EVIDENCE` / `DO_NOT_PROCEED`); per-finding optional `severity` / `remediation` / `confidence`. 111 tests, CI 에서 live API 호출 0.

**v0.4.x (prompt iteration 트랙)**
- 다양한 실제 repo (Python, TypeScript, Go) 에 dogfood. Classification 에러가 군집하는 곳을 찾아 anti-pattern 리스트 tune, 그리고 정직한 REAL finding 을 과도하게 weaken 하는 곳에서 critic sensitivity tune.
- Reference classification-quality benchmark 기록해서 prompt 개정을 추측이 아니라 측정으로. 같은 benchmark 가 critic-pass 비용/이득 수치도 driving — *"critic 호출이 결정 level 을 뒤집는 빈도는?"* 이 답할 수 있는 질문이어야 함.

**v0.5 (도구 깊이)**
- OpenAI adapter 에 `o1` / `o3`-class 모델용 reasoning-effort passthrough.
- `antemortem diff` — 같은 doc 의 두 run 을 비교, 어떤 classification 이 이동했는지, 어떤 critic status 가 변경됐는지, decision level 이 시프트했는지 surface.
- 반복 same-repo run 을 위해 files block 에 두 번째 `cache_control` breakpoint.
- CI lint gating 용 공식 GitHub Action.

**v1.0 (계약 lock)**
- Public schema 버저닝 (`antemortem.schema.json` 별도 publish).
- Output JSON shape, decision enum, exit-code 계약에 대한 semver 보장.
- JSON artifact 의 HTML renderer (printable debrief view).

**명시적 out of scope** (v0.4 이후 포함): 웹 대시보드, DB-backed 히스토리, 멀티유저 tenancy, proprietary hosting.

전체 changelog: [CHANGELOG.md](CHANGELOG.md).

---

## 기여

Case study 는 [Antemortem methodology repo](https://github.com/hibou04-ops/Antemortem) 의 `examples/` 아래 PR 로 — 가장 가치 있고 가장 만들기 어려운 기여. Bar: *"모든 classification 이 `file:line` 인용, post-implementation 노트 존재, recon 이 놓친 것에 정직할 것."*

도구 레벨 기여 (새 CLI flag, 스키마 필드, prompt 수정) 는 이 repo 의 `main` 대상 PR. 가능하면 해당 변경에 대한 antemortem 문서 첨부 — 도구는 자기 자신의 개발에 dogfood 됨.

---

## 인용

```
antemortem-cli v0.4.0 — tooling for the Antemortem pre-implementation reconnaissance discipline.
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

Solo 로 설계, 구현, ship. `commands/` 및 `providers/` subpackage 전반 16개 모듈, 111 tests, CI 에서 live API 호출 0. 이 도구는 자신을 build 하는 변경사항들을 classify — dogfood 가 first-class 테스트 surface.
