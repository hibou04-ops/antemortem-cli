# antemortem-cli (한국어)

Antemortem은 diff를 쓰기 전에 구현 계획의 리스크가 `REAL`, `GHOST`, `NEW`, `UNRESOLVED` 중 무엇인지 확인하는 CLI입니다. 사용자가 spec, trap, 읽을 repo 파일을 먼저 정하면, CLI는 그 파일만 provider에 보내고 schema-constrained output을 요구합니다. `UNRESOLVED`가 아닌 판단에는 디스크에서 검증 가능한 `file:line` citation이 필요하며, `lint`가 schema, citation, evidence binding을 repo와 다시 대조합니다.

[![CI](https://github.com/hibou04-ops/antemortem-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/hibou04-ops/antemortem-cli/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![PyPI](https://img.shields.io/badge/pypi-0.10.2-blue.svg)](https://pypi.org/project/antemortem/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](#상태--로드맵)
[![Tests](https://img.shields.io/badge/tests-offline%20CI-brightgreen.svg)](tests/)
[![Providers](https://img.shields.io/badge/providers-anthropic%20%7C%20openai%20%7C%20gemini%20%7C%20openai--compatible-informational.svg)](#provider-지원)
[![Methodology](https://img.shields.io/badge/methodology-Antemortem-blueviolet.svg)](https://github.com/hibou04-ops/Antemortem)

**이럴 때 사용합니다**

- 위험한 refactor를 시작하기 전
- agent-generated patch를 만들기 전
- 구현 계획을 merge하기 전
- 큰 변경을 CI gate에 걸기 전

**Trust loop**

- `doctor`: provider 호출 전에 무엇을 parse, read, send할지 미리 확인합니다.
- `run`: `REAL` / `GHOST` / `NEW` / `UNRESOLVED` classification이 담긴 structured recon artifact를 만듭니다.
- `lint`: schema, citation, path bounds, evidence hash/snippet을 디스크와 대조합니다.
- `evidence`: provider 호출 없이 기존 artifact의 evidence hash를 점검하거나 누락분만 채웁니다.
- `eval`: committed offline golden case로 harness를 측정합니다.
- `gate`: CI에서 decision policy를 강제합니다.

일반적인 AI 코드 리뷰는 diff나 chat prompt에서 시작합니다. Antemortem은 diff 이전의 계획에서 시작하고, 모델이 코드를 보기 전에 사람이 trap을 먼저 쓰게 하며, 근거 없는 출력을 그럴듯한 의견이 아니라 invalid output으로 다룹니다.

CLI 명령은 7개입니다: `init` / `doctor` / `run` / `lint` / `evidence` / `gate` / `eval`.

```bash
pip install antemortem
```

> **현재 릴리스: v0.10.2** — 공개 README claim은 `python scripts/check_repo_consistency.py`로 source of truth와 대조합니다.

English README: [README.md](README.md)

생성된 source-of-truth claim block: [English](docs/generated/claims.md) · [Korean](docs/generated/claims_kr.md).

신뢰 모델: [한국어](docs/trust_model_kr.md) · [English](docs/trust_model.md).

Toolkit positioning: [한국어](docs/toolkit_positioning_kr.md) · [English](docs/toolkit_positioning.md).

Claim ledger: [한국어](docs/claim_ledger_kr.md) · [English](docs/claim_ledger.md).

CLI examples: [한국어](docs/examples_kr.md) · [English](docs/examples.md).

Provider 지원: Anthropic / Claude, OpenAI, Gemini, 그리고 structured-output `parse` path를 지원하는 OpenAI-compatible endpoint. 로컬 또는 일부 호환 endpoint는 아래 [Provider 지원](#provider-지원)과 FAQ의 제약을 먼저 확인하십시오.

---

## Demo (60s)

https://github.com/user-attachments/assets/7ccb714e-2162-4933-aee0-64855aa58f97

> `examples/demo_recon.py`의 60초 walkthrough: 4개 trap → `REAL` / `GHOST` / `NEW` / `UNRESOLVED` classification과 `file:line` citation → `Decision: PROCEED_WITH_GUARDS` → `lint`가 citation을 disk에서 재검증 → 4-level decision gate. 실제 `antemortem lint` output을 읽기 좋게 녹화한 것입니다. 재현 명령: `PYTHONIOENCODING=utf-8 python examples/demo_replay.py`.

이 replay 계약은 `tests/test_demo_replay.py`가 검증합니다. 테스트는 API key 없이 README 명령을 실행하고, label, final decision, lint verification이 `examples/_demo_output.txt`와 맞는지 확인합니다.

---

## 목차

- [Demo (60s)](#demo-60s)
- [이 도구가 해결하는 failure mode](#이-도구가-해결하는-failure-mode)
- [Worked example: 실제 ghost trap](#worked-example-실제-ghost-trap)
- [일곱 커맨드](#일곱-커맨드)
- [Provider 지원](#provider-지원)
- [데이터 계약](#데이터-계약)
- [아키텍처](#아키텍처)
- [Non-trivial 한 설계 결정](#non-trivial-한-설계-결정)
- [이것은 아닙니다](#이것은-아닙니다)
- [비용 및 성능](#비용-및-성능)
- [검증](#검증)
- [Toolkit positioning](#toolkit-positioning)
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
2. **UNRESOLVED 가 아닌 모든 classification 이 `file:line` 인용 보유.** 스키마는 SDK 경계에서 Pydantic-enforced 이고, `antemortem lint` 가 모든 citation 을 disk 에서 재검증. `evidence_hash` 또는 `evidence_snippet` 이 있으면 cited text binding 도 검증합니다.

이 두 가드레일 없이는 다른 형태의 hand-waving 으로 교환한 것뿐입니다. 두 가드레일이 있으면 schema validation, citation lint, evidence binding 으로 claim 을 다시 확인할 수 있는 mechanical screening step 이 됩니다.

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

## 일곱 커맨드

### `antemortem init <name>`

공식 템플릿으로부터 문서를 스캐폴드. YAML frontmatter (`name`, `date`, `scope`, `reversibility`, `status`, `template`) + 7개 섹션 본문. `--enhanced` 는 더 풍부한 템플릿으로 교체: calibration 차원 (evidence strength, blast radius, reversibility), 세분화된 classification subtype (`REAL-structural`, `GHOST-mitigated`, `NEW-spec-gap`, …), 모든 REAL/NEW finding 에 대한 명시적 skeptic pass, decision-first output 구조.

```bash
antemortem init my-feature                  # basic
antemortem init prod-migration --enhanced   # 고-stakes 변경용
```

템플릿은 [Antemortem](https://github.com/hibou04-ops/Antemortem) 에서 Apache 2.0 으로 vendoring.

### `antemortem doctor <doc>`

Provider 호출 전에 작성한 recon 문서를 preflight 합니다. Frontmatter 와 trap table 을 parse 하고, `run` 과 같은 file safety policy 를 적용하고, 누락/제외 파일, payload 크기, `READY` / `READY_WITH_WARNINGS` / `NOT_READY` 상태를 출력합니다.
`--json-output <path>` 를 명시하지 않으면 artifact 를 쓰지 않습니다.

```bash
antemortem doctor antemortem/my-feature.md --repo .
antemortem doctor antemortem/my-feature.md --repo . --json
```

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

**선택적 second pass — `--critic`.** Critic 은 REAL 및 NEW finding 을 같은 evidence 에 대조해 재검토하고 `CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE` 중 정확히 하나를 반환. 전용 ~1.5k-token critic prompt 는 명시적으로 비대칭: critic 은 오직 downgrade 만 가능. `WEAKENED` → `UNRESOLVED`; `CONTRADICTED` → counterevidence 에 따라 `GHOST` 또는 `UNRESOLVED`; `DUPLICATE` → drop; `CONFIRMED` → 그대로. 이 second pass 는 새 finding 을 만드는 경로가 아니라 보수적 review filter 입니다. 기본 꺼짐. False REAL 이 비싼 변경에서 켤 것.

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
| **추론 / thinking** | Adapter-specific. Anthropic adapter 는 기본으로 adaptive thinking + `effort: high`. OpenAI/Gemini adapter 는 Anthropic 전용 thinking knob 을 제거. | Provider adapter 가 지원하는 범위에서만 설정 가능; 미지원 knob 은 provider 경계를 넘기지 않음. |
| **Sampling 손잡이** | 인터페이스에서 제외. | Discipline 은 temperature / top_p 에 의존 안 함. Adapter 들이 이를 send 안 함. |
| **Refusal 처리** | Actionable 메시지와 함께 `ProviderError` raise. | Anthropic: `stop_reason == "refusal"`. OpenAI: `finish_reason == "content_filter"`. |
| **파일 로딩** | `--repo` root, path-traversal 거부, UTF-8 + replace fallback. | Provider 간 동일; discipline 자체의 보장. |

Markdown 문서 자체는 **수정되지 않습니다**. JSON artifact 가 machine-readable output. `lint` 가 artifact 를 disk 대조 검증. 이 분리는 parsing bug 가 markdown 을 손상시키는 것을 막습니다.

### `antemortem lint <doc>`

CI 에 composable 한 두 단계 검증:

1. **Pre-run (schema)**: frontmatter parse, spec 섹션 텍스트 존재, 최소 하나의 trap enumerate, Recon protocol 아래 최소 하나의 파일. 모든 문서에 적용.
2. **Post-run (citations)**: 문서 옆 `<doc>.json` 존재 시 — 모든 input trap 에 classification, 모든 classification 에 유효한 `path:line` 또는 `path:line-line` 인용, 모든 인용 파일이 `--repo` 에 존재, 모든 line range 가 해당 파일의 bounds 내. `evidence_hash` 가 있으면 cited source text 에서 재계산하고, `evidence_snippet` 이 있으면 cited range 안에 존재해야 합니다.

통과 시 exit `0`, 실패 시 `1`, 모든 violation 을 한 줄씩 출력. CI 게이트로: *"그 PR 의 antemortem 이 lint clean 하지 않으면 merge 불가."*

### `antemortem evidence <artifact.json>`

기존 artifact를 읽고 현재 repo checkout에서 evidence hash를 다시 계산합니다. Missing hash, matching hash, mismatch, snippet mismatch, oversized range, invalid citation을 보고합니다. Provider 호출은 없습니다.

```bash
antemortem evidence antemortem/my-feature.json --repo .
antemortem evidence antemortem/my-feature.json --repo . --check
antemortem evidence antemortem/my-feature.json --repo . --write-missing
```

`--write-missing`은 citation validation이 통과한 항목의 비어 있는 `evidence_hash`만 채웁니다. Mismatch hash는 덮어쓰지 않습니다.

---

## Provider 지원

`antemortem-cli`는 LLMProvider Protocol을 통해 LLM과 통신합니다. Discipline은 vendor-neutral이며 하나의 provider seam만 pluggable입니다. 각 adapter는 아래 structured-output path를 사용하고, 반환된 artifact object는 write 전에 Pydantic으로 검증됩니다. 파이프라인 어디에도 클라이언트 측 JSON regex-parsing은 없습니다. 이 matrix는 `src/antemortem/providers/capabilities.py`와 대조됩니다. 자세한 내용은 [Provider Compatibility](docs/provider_compatibility.md)를 보십시오.

<!-- provider-matrix:start -->
| Provider | CLI | 기본 model | API key env | Structured output path | Contract-tested behavior | Caveats |
|---|---|---|---|---|---|---|
| Anthropic | `--provider anthropic` | `claude-opus-4-7` | `ANTHROPIC_API_KEY` | `messages.parse(output_format=...)` | Pydantic validates parsed/dict output before artifact write. SDK exceptions and refusals surface as ProviderError. | Native Anthropic only; base_url is ignored. |
| OpenAI | `--provider openai` | `gpt-4o` | `OPENAI_API_KEY` | `beta.chat.completions.parse(response_format=...)` | Pydantic validates parsed/dict output before artifact write. SDK exceptions, content_filter, missing choices, and missing parsed output surface as ProviderError. | Requires models/endpoints that support the SDK structured parse path. |
| Gemini | `--provider gemini` | `gemini-2.5-flash` | `GEMINI_API_KEY` / `GOOGLE_API_KEY` | `Google GenAI response_schema with application/json` | Returned JSON is parsed and validated with the same Pydantic artifact schema. SDK exceptions, invalid JSON, schema errors, safety blocks, and missing candidates surface as ProviderError. | Requires Google GenAI SDK; no OpenAI-compatible base_url path. |
| OpenAI-compatible | `--provider openai --base-url <url>` | `user-supplied via --model` | `OPENAI_API_KEY` / `or any string for unauthenticated local endpoints` | `Same OpenAI parse path via configured base_url` | Pydantic validates parsed/dict output before artifact write. Same OpenAI adapter ProviderError handling. | Not universal: endpoint must implement the structured parse path; local model fidelity varies and lint remains mandatory. |
<!-- provider-matrix:end -->

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
    # ↓ critic.py 가 채움, --critic 전달 시에만
    critic_results=[
        CriticResult(
            finding_id="t1",
            status="CONFIRMED",
            issues=[],
            counterevidence=[],
            recommended_label=None,
        ),
    ],
    # ↓ decision.py 가 채움, --no-decision 으로 억제
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
│                        severity?, confidence?, remediation?, │
│                        evidence_snippet?, evidence_hash?)    │
│    new_traps[]        (hypothesis, citation, note,            │
│                        evidence_snippet?, evidence_hash?)    │
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
│  citations.py → path:line + evidence binding 을 disk 검증   │
│  exit 0 = classifications 신뢰 가능                          │
│  exit 1 = 뭔가 fabricated 이거나 out of date                 │
└──────────────────────────────────────────────────────────────┘
```

모든 모듈이 단일 책임; 파이프라인은 네트워크 없이 end-to-end 테스트 가능. `AntemortemDocument`, `Classification`, `NewTrap`, `CriticResult`, `AntemortemOutput` 이 데이터 계약 — 같은 타입이 `run` 에서 `critic`, `decision` 을 거쳐 `lint` 까지 흐르므로 한쪽의 drift 가 다른 쪽들에서 잡힘.

---

## Non-trivial 한 설계 결정

**Vendor-neutral 인터페이스, vendor-native adapter.** `LLMProvider` Protocol은 한 메서드이고 vendor-specific knob을 노출하지 않습니다. 각 adapter는 `src/antemortem/providers/capabilities.py`에 등록된 structured-output path를 사용합니다: Anthropic `messages.parse`, OpenAI `beta.chat.completions.parse`, Gemini `response_schema`와 local Pydantic validation. Discipline(Pydantic enforcement, disk-verified citations, stable exit codes)은 provider 간 동일합니다. 새 provider 추가는 한 모듈, capability entry, contract tests를 추가하는 일이며 CLI나 data contract를 건드리지 않습니다.

**System prompt 는 provider-neutral 하게 작성.** `src/antemortem/prompts.py` 의 ~5k 토큰 `SYSTEM_PROMPT` 는 특정 vendor, 모델, API surface 를 참조하지 않음. LLM 이 만족해야 할 항목 (네 개의 정확한 라벨 정의, good/bad 예시가 있는 citation rule, scope 경계, few-shot JSON 예시) 으로 discipline 을 정의. Provider 교체 시 re-tuning 불필요.

**Citation 은 `lint` 가 disk 에서 검증, 신뢰하지 않음.** Structured-output API 는 refusal 하에서 schema conformance 를 깰 수 있고, 잘 동작하는 모델도 긴 파일에서 가끔 line 을 miscount. 모델의 self-report citation 을 신뢰하는 것은 테스트된 PR 이 버그 없다고 믿는 것과 같은 실수. 방어는 소스 대조 재검증: path bounds 는 항상, `evidence_hash` 와 `evidence_snippet` 은 존재할 때 검증. `lint` 는 first-class 커맨드 — CI 게이트가 ceremony 없이 돌릴 수 있어야 하므로.

**JSON artifact 가 출력, markdown 이 입력.** 모델이 markdown 을 in-place 로 편집할 수 있음 — 어떤 도구는 그렇게 함. 우리는 안 함, 세 가지 이유로: (1) markdown 은 당신 것이지 모델 것 아님; (2) 어느 방향이든 parse bug 가 수 시간의 작업을 corrupt 할 수 있음; (3) machine-readable JSON 은 downstream tooling (CI 게이트, 대시보드, diff 뷰어) 과 깔끔하게 compose. Markdown 은 human artifact 로 유지.

**~5k 토큰 system prompt, 의도적.** Anthropic 과 OpenAI 모두 각자의 threshold 를 넘는 prefix 를 cache; prompt 는 양쪽 모두 넉넉히 넘도록 sized. 더 짧으면 신뢰할 만하게 cache 안 됨; 더 길면 enforce 하는 discipline 으로부터 drift. 모든 substantive 바이트가 load-bearing: role framing, input format, 네 라벨의 정확한 정의, good/bad 예시가 있는 citation rule, anti-pattern 리스트, scope 경계, 네 개의 few-shot JSON 예시. [전체 prompt](src/antemortem/prompts.py) 는 prompt-cache-aware 설계 사례.

**Pydantic v2 스키마가 데이터 계약, dict-모양 comment 아님.** `Classification`, `NewTrap`, `AntemortemOutput`, `Frontmatter`, `AntemortemDocument` 모두 end-to-end 흐름: SDK 가 API 경계에서 검증, `run` 이 검증된 JSON 을 쓰고, `lint` 가 load 시 검증. Malformed classification 은 disk 에 절대 쓰이지 않음 — 즉, main 에 merge 되지 않음.

**Windows path 정규화는 cache-invariant, cosmetic 아님.** `src\foo.py` 와 `src/foo.py` 는 disk 에서 같지만 API payload 에서는 다른 바이트입니다. Provider cache key 는 byte-exact 일 수 있으므로 content 가 build 되기 전 모든 path 는 forward slash 로 정규화합니다. `api.py:_build_user_content` 참조.

**Exit code는 안정된 계약입니다.** `1`은 validation failure, `2`는 usage/configuration error, `3`은 신뢰 가능한 artifact를 쓰기 전 provider call이 실패한 경우, `4`는 gate 또는 benchmark threshold가 policy로 막은 경우입니다. 전체 표는 [CLI Exit Codes](docs/cli_exit_codes.md)에 있습니다.

**Scope 경계는 prompt 에서 enforced, 제안 아님.** System prompt 는 명시적으로 말함: *"You classify what is in the provided files. You do not: speculate about files not shown, comment on architecture beyond the spec's scope, recommend the user adopt a different design, evaluate whether the change is a good idea."* 사용자가 위 중 하나를 요청하면 모델은 `spec_mutations` 에 "Out of antemortem scope" 로 기록하고 진행하도록 지시받음. 이 도구는 한 가지만 함.

**Critic pass 는 비대칭 — downgrade 만.** `--critic` 이 두 번째 provider 호출을 추가. 해당 prompt (~1.5k 토큰, classifier prompt 와 격리) 는 모델에게 모든 REAL 및 NEW finding 을 adversarially 재검토하고 `CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE` 중 하나를 반환하도록 지시. 이 status 들을 소비하는 정책은 의도적으로 한 방향: finding 은 REAL / NEW *에서* UNRESOLVED / GHOST / drop *으로* 움직일 수 있고 반대 방향은 절대 없음. 대칭적 critic 은 자신의 signal 을 오염시킬 수 있습니다. Critic 이 UNRESOLVED 를 REAL 로 promote 할 수 있으면 noisy critic 이 finding 을 새로 만들 수 있기 때문입니다. 비대칭은 second pass 를 보수적으로 유지하고 비용 모델을 provider 호출 1회 추가로 고정합니다.

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

**Offline test suite, normal CI 에서 네트워크 호출 0.** `python -m pytest -q`로 실행합니다. 모든 provider 는 `LLMProvider` Protocol 로 받음 — 모든 API 테스트는 `SimpleNamespace` 나 `MagicMock` 으로 client 를 mock. 두 가지 benefit: API 크레딧 소비 없는 결정론적 CI, 그리고 실제 서버와 협상 없이 request payload 의 *정확한* shape (model, thinking config, cache_control 배치, `response_format`, 정렬된 파일 순서) 을 assert 할 수 있는 테스트-시점 자유도.

| 모듈 | 커버리지 |
|---|---|
| `schema.py` | 11 tests — 필수 필드, label enum, UNRESOLVED 의 nullable citation, evidence binding fields, NewTrap id pattern, JSON roundtrip. |
| `citations.py` | 14 tests — range 파싱, Windows backslash 정규화, 빈 문자열 / prose / zero-line / reversed-range 거부, path traversal 포함 disk 검증. |
| `evidence_hash.py` | 14 tests — evidence hash 정규화, strict-evidence lint, snippet mismatch, source drift detection, traversal-safe hash 계산, run-time local hash stamping. |
| `evidence_command.py` | 5 tests — write-missing behavior, path traversal rejection, source drift detection, stable JSON output, UNRESOLVED handling. |
| `adversarial_boundaries.py` | 7 tests — recon file list/citation path traversal, symlink escape, hidden secret file/binary/huge/invalid encoding 처리, malformed table, duplicate trap ID, empty spec/no traps/no files. |
| `claim_ledger.py` | 5 tests — current ledger validity, missing source detection, qualitative marker enforcement, location drift detection, README ledger-link coverage. |
| `demo_replay.py` | 3 tests — README replay command, `demo_recon.py` 대비 저장된 capture freshness, label/final decision/lint verification demo-doc claim 검증. |
| `examples_gallery.py` | 5 tests — gallery case structure, 모든 artifact offline lint, evidence hash, CI gate blocking behavior, docs link coverage. |
| `github_templates.py` | 3 tests — issue template coverage, trust-context field, PR checklist requirement 검증. |
| `launch_kit_docs.py` | 5 tests — launch note coverage, reproducible command, hype/adoption guardrail, limitation, local link validity 검증. |
| `package_metadata.py` | 5 tests — PyPI description length, README content type, project URL, Python classifier/CI parity, PyPI rendering-check docs 검증. |
| `parser.py` | 11 tests — frontmatter 검증, 섹션 추출, `recon-protocol` vs `pre-recon` 구분, placeholder-row 필터링과 trap 테이블 파싱. |
| `lint.py` | 11 tests — 두 단계 (schema-only 와 artifact), 모든 violation 경로, exit code. |
| `post_release_check.py` | 8 tests — mocked PyPI/GitHub success path, dry-run/skip-network mode, PyPI/tag/install failure, local docs coverage, stable JSON, analytics wording guardrail 검증. |
| `providers/` | 29 tests — factory 가 알 수 없는 이름 거부, 기본값 사용, `--base-url` passthrough; Anthropic adapter 가 예상 kwargs build / refusal raise / dict-output coerce; OpenAI adapter 가 `prompt_tokens_details.cached_tokens` → `cache_read_input_tokens` 매핑 / content_filter raise / missing parsed raise; Gemini adapter request shape, local JSON validation, usage metadata mapping. |
| `provider_contracts.py` | 14 tests — capability registry coverage, schema-compatible output accepted, malformed output rejected, provider errors surfaced, offline stub 실행 중 provider SDK import 없음. |
| `api.py` | 5 tests — user-payload shape, Windows path 정규화, provider-delegation 계약, error propagation. |
| `critic.py` | 12 tests — payload 조립 블록 (`<files>`, `<spec>`, `<traps>`, `<first_pass>`), provider-delegation 계약, 네 status 정책 결과 (`CONFIRMED` / `WEAKENED` / `CONTRADICTED` / `DUPLICATE`) 가 first-pass artifact 위에 결정론적으로 적용됨. |
| `decision.py` | 13 tests — 4개 결정 결과 전부, edge case: 빈 classifications, REAL-with-remediation vs REAL-without, severity-high gating, critic-downgrade 상호작용, unresolved-only 입력. |
| `run.py` | 8 tests — 모킹된 provider 로 전체 흐름, 에러 경로, 경고, JSON-summary env var, cache-miss 경고 surface, critic pass 위임. |
| `doctor.py` | 6 tests — READY preflight, missing file failure, duplicate trap id strictness, path traversal rejection, binary file skip, stable JSON output. |
| `init.py` | 6 tests — basic + enhanced 템플릿, `--force`, path traversal 거부, ISO 날짜 frontmatter. |
| `eval_benchmarks.py` | 9 tests — JSON/table output, threshold failure, unknown threshold rejection, golden-case directory contract, adversarial case coverage, denominator checks, malformed-case isolation, provider construction 없음. |
| `repo_consistency.py` | 7 tests — version mismatch, stale decision enum, stale command count, allowlisted historical reference, exact public test-count rejection, provider matrix drift 검증. |
| `generate_readme_claims.py` | 5 tests — command-registry drift, generated-claim freshness detection, Korean/English enum parity, benchmark JSON ingestion, platform-independent claim rendering 검증. |
| `generate_release_notes.py` | 4 tests — explicit-file fallback, git-range input, benchmark JSON-only metrics, `--output` CLI behavior. |
| `rc_freeze_check.py` | 4 tests — release-audit coverage, static failure inventory, stale `dist/` detection, parent release-audit mode. |
| `release_audit.py` | 4 tests — mocked success path, first-failure exit, stable JSON summary, continue-on-error failure inventory. |
| `scope_freeze_check.py` | 6 tests — current public docs, feature-promise detection, unimplemented command detection, deferred roadmap allowance, comparative-claim guardrail, allowlist behavior. |
| `smoke_wheel_install.py` | 10 tests — mocked wheel build/install path, build failure stop, missing fixture failure, package-data boundary documentation, missing package module, installed CLI failure, version mismatch, tooling blocker 검증. |
| `ci_workflow.py` | 4 tests — workflow name/badge parity, supported Python matrix, offline trust commands, separate wheel-smoke job without provider API keys. |
| `cli.py` | 3 tests — `--help` 가 등록된 command surface 를 나열, `--version`, no-args-prints-help. (커맨드별 동작은 `run.py` / `lint.py` / `init.py` / `gate.py` 에서 커버.) |
| `cli_help_text.py` | 5 tests — 모든 command help snapshot, README Quick Start command parity, actionable `FAIL` / `Why` / `Next` messages, policy exit codes, exit-code docs와 constants 일치. |
| `trust_model_docs.py` | 3 tests — trust model topic coverage, README link coverage, unbacked comparative claim language 부재 검증. |
| `toolkit_positioning_docs.py` | 4 tests — toolkit role coverage, README link coverage, local/external link allowlist, hype-claim guardrail 검증. |

`python -m pytest -q` 로 실행합니다. Generated public claim block은 OS/Python matrix별 pytest collection 차이를 피하기 위해 exact collected test count를 공개 claim으로 두지 않습니다.

## Repository self-checks

```bash
python scripts/generate_readme_claims.py --check
python scripts/check_repo_consistency.py
```

Generated claim block과 README 버전, badge, command count/name, decision enum, package name, provider row, benchmark-backed claim 을 `pyproject.toml`, Typer app, `decision.py`, provider registry, benchmark JSON 과 대조합니다.

Release readiness는 전체 local audit로 확인합니다.

```bash
python scripts/release_audit.py
```

이 명령은 tests, generated-claim checks, offline benchmark, build, `twine check`, installed-wheel smoke test를 실행하지만 publish는 하지 않습니다. 자세한 내용은 [Release Hygiene](docs/release_hygiene.md)을 보십시오.

GitHub Actions workflow `CI`는 supported Python version에서 Ubuntu/Windows offline trust checks를 실행하고 benchmark JSON을 artifact로 업로드하며, wheel smoke install은 별도 job에서 실행합니다. 일반 CI에는 provider API key가 필요 없습니다.

wheel entrypoint만 직접 검증하려면:

```bash
python scripts/smoke_wheel_install.py
```

## Benchmark-backed claims

```bash
antemortem eval benchmarks/golden_cases --json
```

Committed golden benchmark set 은 `trap_label_accuracy`, `new_trap_precision`, `citation_valid_rate`, `false_real_rate`, `false_ghost_rate`, `unresolved_rate`, `decision_accuracy`, `critic_flip_rate`, `high_severity_block_rate`, `schema_parse_success_rate` 를 stored output 기준으로 측정합니다. Harness 는 offline 입니다. `provider_output.json` 을 읽고 같은 Pydantic artifact schema 로 검증하며, 각 fixture `repo/` 에 대해 citation 을 확인하고, `expected.json` 과 비교합니다.

Committed case에는 evidence snippet drift, 너무 넓은 citation range, path traversal citation, binary-file skip, link escape attempt, duplicate trap id, `UNRESOLVED`로 남아야 하는 missing file, evidence hash가 있는 `NEW` trap, exact-line `GHOST` evidence, high-severity `REAL` blocker fixture가 포함됩니다.

현재 fixture set 에 대해 invariant 로 둘 metric 은 CI threshold 로 고정할 수 있습니다.

```bash
antemortem eval benchmarks/golden_cases \
  --fail-under decision_accuracy=0.8
```

이 수치는 committed golden case 에 대한 repo-local measurement 입니다. 다른 도구보다 우월하다는 주장이나 일반 model quality 주장으로 읽으면 안 됩니다.

---

## Evidence-bound citations

Line-bound citation check는 location 존재를 증명합니다. Evidence-bound check는 artifact 생성 뒤 cited source text가 drift하지 않았음을 검증합니다.

`antemortem run`은 citation validation 뒤 `evidence_hash`를 로컬에서 계산합니다. 모델에게 hash 생성을 요구하지 않습니다. Hash format은 `sha256:<hex>`이며, cited line range를 LF로 정규화하고 trailing whitespace만 제거한 텍스트의 SHA256입니다. `evidence_snippet`이 있으면 `lint`가 해당 snippet이 cited range 안에 있는지 확인합니다.

기본 lint는 `evidence_hash`가 없는 기존 artifact와 호환됩니다. CI에서는 strict evidence를 권장합니다.

```bash
antemortem lint antemortem/my-feature.md --repo . --strict-evidence
```

기존 artifact에 유효한 citation은 있지만 hash가 없을 때는 `antemortem evidence <artifact.json> --repo . --write-missing`를 사용합니다. 그 다음 `lint --strict-evidence`로 누락되거나 stale한 hash가 없는지 강제하십시오. Evidence command는 maintenance tool이고, strict lint가 CI gate입니다.

---

## Toolkit positioning

이 저장소는 구현 전 reconnaissance를 위한 CLI/CI 검증 표면입니다. 이 repo가 맡는 범위는 다음입니다.

- 코드 변경 전 risk classification
- citation/evidence가 검증된 artifact
- 로컬 `doctor` / `lint` / `evidence` / `eval` / `gate` check

관련 도구는 인접 도구이며 prerequisite가 아닙니다.

- `omegaprompt`: calibration / optimization layer
- `omega-lock`: audit / post-optimization lock layer
- `mini-omega-lock`: empirical live API preflight
- `mini-antemortem-cli`: deterministic analytical preflight, if applicable

역할 경계와 claim boundary는 [Toolkit Positioning](docs/toolkit_positioning_kr.md)에 정리되어 있습니다. 이 README는 배포되는 CLI에 집중합니다.

---

## 회의론자를 위한 FAQ

**이건 그냥 pre-mortem (Klein, 2007) 을 새 이름으로 한 것 아닌가요?**

아닙니다. Gary Klein 의 pre-mortem 은 *팀-수준 전략적 연습* ("우리가 실패했다고 가정; 원인은?") 으로 프로젝트 commit 시점에 30–60분 소요. Antemortem 은 *change-수준, 솔로, 소스-코드-기반, 전술적*, 15–30분에 discharged. Pre-mortem 은 *"해야 하나?"* 를 묻고, Antemortem 은 *"할 것이니, 기존 코드가 이 특정 접근의 리스크에 대해 이미 뭘 말하는가?"* 를 물음. 그들은 compose — pre-mortem 먼저, antemortem 은 per-change.

**그냥 LLM 에게 "내 spec 리뷰해줘" 하면 되지 않나?**

그게 이 도구가 방지하려는 degenerate case. 두 가드레일 없이는 LLM 이 당신이 쓴 것에 기꺼이 동의. 일반적 리스크와 진짜 리스크가 섞인 리스트를 받고, 어느 게 어느 건지 구분할 수 없고, 모델이 주장을 뒷받침하도록 압박이 없음. `file:line` 요구 + `lint` 의 재검증이 "의견" 과 "증거" 의 차이.

**모델 선택이 중요한가요?**

Discipline 은 설계상 vendor-neutral 이지만 모델 능력은 중요. 이 도구는 모델에게 multi-file call chain 추적, 정확한 `file:line` citation 으로 분류, 엄격한 JSON 스키마 준수를 요구. Frontier-tier 모델 (Anthropic Opus-class, OpenAI `gpt-4o` 이상, 또는 유능한 로컬 reasoner) 이 이 bar 통과; 작은 모델은 더 많은 UNRESOLVED 라벨 생성 가능 — 여전히 valid 한 결과이지만 덜 유용. `lint` 가 모델 관계없이 조작된 citation 을 mechanical 로 잡으므로 약한 모델의 최악 케이스는 "low signal" 이지 "wrong signal" 이 아님.

**모델이 line number 를 그냥 지어낼 건데?**

가끔 그럴 것. 그래서 `lint` 가 존재. 모든 citation 이 parsed, 파일이 load, line range 가 실제 파일 bound 와 대조. `evidence_hash` 또는 `evidence_snippet` 이 있으면 cited source text 도 검증. 할루시네이트된 citation 은 lint fail. 모델은 *"A fabricated line number is strictly worse than UNRESOLVED — UNRESOLVED is honest, fabrication is not"* 라고 지시받고, discipline 이 mechanical 검증으로 이를 backup.

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

OpenAI-compatible endpoint는 SDK의 structured-output `parse` path를 구현한 경우에만 `--base-url`로 사용할 수 있습니다. Ollama의 compatibility layer `http://localhost:11434/v1`는 reachable하지만, structured-output fidelity는 model별로 다릅니다.

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

v0.10.2 는 **alpha**. CLI 계약 (seven commands, flags, exit codes) 은 stable. JSON artifact schema 는 alpha line 안에서 additive 를 우선합니다. Breaking output-shape 변경은 명시적 contract-lock release 로 미룹니다. Prompt iteration 은 offline test, 기록된 artifact, 또는 문서화된 replay command 로 검증 가능한 경우에만 진행합니다.

Semver 는 v1.0 부터 엄격 적용.

**Shipped**
- **v0.2** — 스캐폴드 (`init`), 분류 (`run`, Claude Opus 4.x 대상), lint (schema + disk-verified citation). 토대가 된 세-커맨드 CLI surface.
- **v0.3** — `LLMProvider` Protocol 과 `providers/` 패키지; vendor-native structured-output path를 쓰는 Anthropic / OpenAI adapter; `--base-url` 로 OpenAI structured `parse` path를 구현한 compatible endpoint 연결.
- **v0.4** — `--critic` 비대칭 second-pass 리뷰 (downgrade 만); 4-level decision gate (`SAFE_TO_PROCEED` / `PROCEED_WITH_GUARDS` / `NEEDS_MORE_EVIDENCE` / `DO_NOT_PROCEED`); per-finding optional `severity` / `remediation` / `confidence`.

**Current release-hygiene track**
- `python scripts/check_repo_consistency.py` 로 공개 README claim 을 source of truth 에 묶습니다.
- 실제 repo dogfood 결과는 artifact 또는 재현 가능한 command 로 남깁니다.
- 정량적 prompt-quality claim 전에는 classification-quality benchmark fixture 를 먼저 둡니다.

**Next measurement track**
- Prompt revision 과 critic-pass cost/benefit 을 위한 benchmark fixture 추가.
- Artifact comparison contract 가 test 로 고정된 뒤에만 run-diff command 추가.
- 반복 same-repo run 을 위해 files block 에 두 번째 `cache_control` breakpoint.
- CI lint gating 용 공식 GitHub Action.

**v1.0 (계약 lock)**
- Public schema 버저닝 (`antemortem.schema.json` 별도 publish).
- Output JSON shape, decision enum, exit-code 계약에 대한 semver 보장.
- JSON artifact 의 HTML renderer (printable debrief view).

**명시적 out of scope**: 웹 대시보드, DB-backed 히스토리, 멀티유저 tenancy, proprietary hosting.

전체 changelog: [CHANGELOG.md](CHANGELOG.md).

---

## Troubleshooting

**`antemortem run`이 401 / Incorrect API key 리턴.** provider SDK가 키는 받았지만 invalid한 경우. 각 provider는 자기 환경변수만 읽습니다 — vendor 간 fallback 없음:

| Provider | 허용 환경변수 |
|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `gemini` | `GEMINI_API_KEY` **또는** `GOOGLE_API_KEY` (먼저 set된 것이 우선) |

발급 dashboard (Anthropic / OpenAI / [Google AI Studio](https://aistudio.google.com/apikey) for Gemini)에서 키 회수/재발급 후 재export.

**`ProviderError: Gemini API key is required`.** `GEMINI_API_KEY`도 `GOOGLE_API_KEY`도 set되지 않은 경우. free-tier key는 <https://aistudio.google.com/apikey>.

**API 비용 쓰기 전 sanity check.** deterministic replay를 먼저 (키도 네트워크도 불필요):

```bash
PYTHONIOENCODING=utf-8 python examples/demo_replay.py
antemortem lint examples/demo_antemortem.md --repo .
```

여기 통과하면 그 다음에 live `antemortem run`으로.

**Citation은 그럴듯한데 `lint`가 fail한다.** 모델이 disk에 없는 `file:line`을 fabricate한 경우 — `lint`가 잡으려고 만든 정확히 그 failure mode. `--strict-citations`를 넣어 unresolvable citation이 있으면 gate 시점이 아니라 upfront에서 fail시키세요.

---

## 기여

Case study 는 [Antemortem methodology repo](https://github.com/hibou04-ops/Antemortem) 의 `examples/` 아래 PR 로 — 가장 가치 있고 가장 만들기 어려운 기여. Bar: *"모든 classification 이 `file:line` 인용, post-implementation 노트 존재, recon 이 놓친 것에 정직할 것."*

도구 레벨 기여 (새 CLI flag, 스키마 필드, prompt 수정) 는 이 repo 의 `main` 대상 PR. 가능하면 해당 변경에 대한 antemortem 문서 첨부 — 도구는 자기 자신의 개발에 dogfood 됨.

---

## 인용

```
antemortem-cli v0.10.2 — tooling for the Antemortem pre-implementation reconnaissance discipline.
https://github.com/hibou04-ops/antemortem-cli, 2026.
```

Methodology:
```
Antemortem methodology — AI-assisted pre-implementation reconnaissance for software changes.
https://github.com/hibou04-ops/Antemortem, 2026.
```

---

## 라이선스

Apache 2.0. [LICENSE](LICENSE) 참조.

**라이선스 히스토리.** 0.2.0, 0.3.0, 0.4.0 PyPI 배포본은 MIT `LICENSE` 파일과 함께 ship 되었습니다. 2026-04-22 (commit `f49af09`) Apache 2.0 으로 재라이선싱되었고, 0.5.0 (2026-04-28) 이후 모든 버전은 Apache 2.0 입니다. 0.4.0 이전을 설치한 사용자는 그 사본에 대해 MIT 라이선스를 보유합니다 — 라이선스 변경은 소급 적용되지 않습니다.

## Colophon

Solo 로 설계, 구현, ship. Offline suite 는 `python -m pytest -q` 로 실행하며, CI 는 mocked provider 를 사용해 live API 호출 0 으로 실행됩니다.
