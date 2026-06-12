# antemortem — AI 에이전트가 정말 당신의 코드를 읽었을까, 아니면 그럴듯하게 말만 한 걸까?

**코딩 에이전트가 계획을 써놓고 당신의 repo에 안전하다고 장담합니다. 증명하게 만드세요.**
`antemortem`은 AI가 모든 주장에 실제 `file:line`을 인용하도록 강제한 뒤, **각 citation을 디스크 위의 실제 바이트와 기계적으로 대조합니다 — 오프라인으로.** 조작된 citation은 검사를 실패시킵니다. 믿어야 할 산문이 아니라, 결정론적 PASS / FAIL이며, CI에서 게이트로 걸 수 있는 명확한 **fabrication rate(조작률)** 숫자가 함께 나옵니다.

[![CI](https://github.com/hibou04-ops/antemortem-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/hibou04-ops/antemortem-cli/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/antemortem?color=blue&label=pypi&cacheSeconds=3600)](https://pypi.org/project/antemortem/)
[![Python](https://img.shields.io/pypi/pyversions/antemortem?cacheSeconds=3600)](https://pypi.org/project/antemortem/)
[![License](https://img.shields.io/pypi/l/antemortem?color=blue&cacheSeconds=3600)](LICENSE)
[![MCP server](https://img.shields.io/badge/MCP-server-blueviolet?cacheSeconds=3600)](#1-주인공-에이전트가-자기-자신을-검사한다-mcp--ci)

> **AI code review · LLM hallucination check · verify AI citations · pre-merge AI plan review · AI agent guardrails · Claude Code / Cursor / Copilot hook · MCP server · GitHub Action**

README family: [English](README.md) · [한국어](README_KR.md) · [Easy start](EASY_README.md) · [쉬운 한국어](EASY_README_KR.md) · Deep docs: [`docs/`](docs/) · [Claim ledger](docs/claim_ledger.md) ([한국어](docs/claim_ledger_kr.md))

```bash
pip install antemortem
```

---

## 한 화면으로 보는 문제

2026년, 당신의 에이전트 — Claude Code, Cursor, Copilot, Aider — 는 계획과 패치를 작성한 뒤, 기존 코드에 대해 안전하다고 자신 있게 말합니다. 하지만 **에이전트가 실제로 repo를 읽었는지, 아니면 안심시키는 답을 환각한 것인지 빠르게 확인할 방법이 없습니다.**

LLM은 유창합니다. 유창함은 증거가 아닙니다. 에이전트는 48번 줄이 뒷받침하지 않는 주장에 `auth/middleware.py:48`을 인용하거나, 존재하지도 않는 줄을 인용합니다. 당신은 런타임에야 그걸 알게 됩니다.

**antemortem은 그것을 잡는 게이트입니다.** 모든 판단을 실제 `file:line`에 근거하도록 강제한 뒤, 인용된 각 줄을 **디스크와 오프라인으로 다시 읽습니다.** 출력은 믿어야 하는 산문이 아니라 기계 검증 가능한 **PASS / FAIL**과 **fabrication rate**입니다:

```text
trap t1: "refresh path leaves the old session cookie live"
  model says: REAL   cite auth/middleware.py:45-52
  antemortem lint → lines 45-52 exist, evidence hash matches disk   ✓ VERIFIED

trap t2: "race on concurrent refresh"
  model says: GHOST  cite auth/token.py:72
  antemortem lint → file has 60 lines; line 72 does not exist       ✗ FABRICATED → exit 1
```

에이전트가 citation을 지어냈다면, 두 번째 경우가 정확히 당신이 보게 되는 것입니다. 그 거짓말은 merge되지 않습니다.

---

## 핵심: 명확한 fabrication-rate 숫자

`antemortem metrics`는 단 하나의 질문 — *모델이 실제 증거를 인용하고 있는가?* — 에 답하고, 그것을 증명하는 숫자를 출력합니다. run artifact를 가리키면 verified vs fabricated vs unresolved citation 수와 **fabrication rate**를 보고하고, 그 비율이 너무 높으면 CI를 실패시킵니다:

```bash
# 모델이 자기 증거를 얼마나 자주 환각했는가?
antemortem metrics antemortem/feat.json --repo .
#   Citations: verified=7, fabricated=1, unresolved=2, cited=8, total=10
#   Fabrication rate: 12.5% of cited
#   Status: FAIL (fabricated citations present)

# CI에서 무관용 — 조작된 citation이 하나라도 있으면 job 실패 (exit 4):
antemortem metrics antemortem/feat.json --repo . --fail-over 0 --format json
```

`--format json`은 안정적인 `antemortem-citation-metrics-v1` 요약을 출력합니다. `--fail-over <rate>`는 `fabricated / cited`가 임계값을 초과하면 `4`(policy gate)로 종료합니다. 이것이 LLM-hallucination 검사를, 감사 가능한 하나의 퍼센트로 압축한 것입니다.

콘솔 한 줄 대신 공유 가능한 artifact가 필요한가요? `antemortem report`는 같은 run을 단일 파일 Markdown 또는 HTML scorecard로 렌더링합니다 — 결정 verdict, trap별 표, citation 검증 상태 — 그리고 자기완결적입니다(HTML은 자체 CSS를 인라인). PR에 첨부하거나 CI artifact로 게시할 수 있습니다:

```bash
antemortem report antemortem/feat.json --repo . --format html --out scorecard.html
```

---

## 1. 주인공: 에이전트가 자기 자신을 검사한다 (MCP + CI)

### 코딩 에이전트에 연결 (MCP server)

`antemortem-mcp`는 [Model Context Protocol](https://modelcontextprotocol.io) server입니다. Claude Code(또는 모든 MCP client)에 꽂으면 에이전트는 merge를 요청하기 전에 **자기 자신의** 출력에 대해 호출할 수 있는 세 개의 도구를 얻습니다:

| MCP tool | 에이전트가 이것으로 하는 일 |
|---|---|
| `scaffold` | 만들려는 변경에 대한 recon 문서를 엽니다. |
| `run` | 각 리스크를 **실제 repo 파일**에 대해 `REAL` / `GHOST` / `NEW` / `UNRESOLVED`로 분류하며, `UNRESOLVED`가 아닌 모든 판단에 `file:line` citation을 답니다. |
| `lint` | **그 citation들을 디스크와 오프라인으로 재검증합니다.** LLM 호출 0회. 모델이 자기 증거를 환각하는 것을 잡습니다. |

MCP server는 정확히 이 세 도구(`scaffold`, `run`, `lint`)만 노출합니다. CI를 향한 표면 — 게이팅, fabrication metrics, scorecard — 는 MCP tool이 아니라 당신의 파이프라인에서 CLI로 실행됩니다. `.mcp.json`(또는 desktop client의 경우 `claude_desktop_config.json`)에 한 번 붙여넣으세요:

```jsonc
{
  "mcpServers": {
    "antemortem": {
      "command": "python",
      "args": ["-m", "antemortem.mcp"],
      "env": { "ANTHROPIC_API_KEY": "sk-ant-..." }
    }
  }
}
```

```bash
pip install "antemortem[mcp]"
```

server는 기본적으로 stdio로 말합니다 — Claude Code가 기대하는 방식입니다. 네트워크 transport가 필요한가요? `python -m antemortem.mcp --http`. `ANTEMORTEM_WORKSPACE_ROOT`로 에이전트의 파일시스템 접근 범위를 한 root 아래로 제한할 수 있어, 에이전트가 넘기는 모든 경로가 그 root 아래로 resolve되어야 합니다. 이제 에이전트는 단지 "repo를 확인했다"고 *말할* 수 없습니다 — 모든 주장이 디스크의 한 줄을 가리키는 artifact를 만들고, 그 줄이 주장을 뒷받침하는지는 `lint`가 결정합니다. **믿어야 하는 self-review가 아니라, 감사할 수 있는 self-review.** 전체 설정은 [`docs/MCP.md`](docs/MCP.md)를 참조하세요.

### CI에서 PR을 막는다 — `uses:` 한 단계

antemortem은 composite **GitHub Action**(repo root의 `action.yml`)을 제공하므로, 전체 게이트가 한 단계입니다 — glue도, 설치 스크립트도 없습니다. PyPI에서 antemortem을 설치하고, 오프라인 `lint` + decision gate를 실행하며, 차단된 결정이나 조작된 citation에서 job을 실패시킵니다:

```yaml
# .github/workflows/antemortem.yml
name: antemortem gate
on: [pull_request]
jobs:
  recon-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hibou04-ops/antemortem-cli@v0.11.0
        with:
          document: antemortem/my-feature.md
          repo: .
          allow: SAFE_TO_PROCEED,PROCEED_WITH_GUARDS
```

Action의 JSON 요약(`schema: antemortem-gate-v1`)은 verdict, decision, fabricated-citation metrics를 담고, 하위 단계를 위해 step `summary` output으로 노출됩니다. raw CLI를 선호하나요? 같은 게이트가 셸 한 줄입니다:

```yaml
      - run: pip install antemortem
      # 이 checkout에 대해 모든 citation을 재검증한 뒤, 정책을 강제한다.
      - run: antemortem gate antemortem/my-feature.md --repo .
```

`antemortem gate`는 먼저 오프라인 `lint`(citation + evidence hash를 디스크와 대조)를 실행한 뒤, **decision allowlist**를 강제합니다. 네 개의 라벨은 결정론적입니다 — 같은 artifact 입력 = 같은 verdict 출력, 모델 호출 없음:

| Decision | 의미 |
|---|---|
| `SAFE_TO_PROCEED` | 남은 실제 리스크 없음. |
| `PROCEED_WITH_GUARDS` | 실제 리스크가 있으나 각각 remediation 있음. |
| `NEEDS_MORE_EVIDENCE` | unresolved가 너무 많거나 citation이 성립하지 않음. |
| `DO_NOT_PROCEED` | mitigation 없는 high-severity 리스크. |

기본 allowlist는 `SAFE_TO_PROCEED,PROCEED_WITH_GUARDS`입니다. exit code는 안정적입니다: `0` pass · `1` validation/citation 실패 · `2` usage error · `3` provider 실패 · `4` policy gate 차단. CI는 exit code로 분기합니다 — 산문을 읽지 않습니다. 전체 레퍼런스는 [`docs/GITHUB_ACTION.md`](docs/GITHUB_ACTION.md)에 있습니다.

### 에이전트가 *실제로* 작성한 패치를 게이트한다

손으로 나열한 파일 범위를 믿지 마세요 — diff에서 유도하세요. `antemortem run --diff <ref>`는 변경된 파일을 git diff에서 바로 읽어 정확히 그 패치를 감사합니다:

```bash
antemortem run antemortem/my-feature.md --repo . --diff origin/main
antemortem gate antemortem/my-feature.md --repo . --format json
```

`--diff`는 `staged`, `working`, 또는 모든 git ref/range(`HEAD~1`, `origin/main`, `a..b`)를 받습니다. 변경된 파일은 recon 범위에 병합됩니다. 그래서 게이트는 에이전트가 언급하기로 *고른* 변경이 아니라 *실제* 변경을 커버합니다.

---

## "그냥 에이전트한테 검토하라고 해" — 그게 지는 이유

무료 경쟁자는 마찰이 없습니다: 에이전트에게 *"이 계획을 repo에 대해 검토해"*라고 하면 합니다. 철저해 *보입니다*. 채점 기준 없이 자기 숙제를 채점하는 AI는 그럴듯한 것을 씁니다. antemortem이 메우는 격차는 다음과 같습니다 — 그리고 post-diff PR-review bot(CodeRabbit, Copilot review 등)과 어떻게 다른지:

| | 에이전트에게 검토 요청 | PR-review bot (CodeRabbit 등) | **antemortem** |
|---|:-:|:-:|:-:|
| 실행 시점 | chat, 임의 | diff가 생긴 **후** | diff **전** — 계획에 대해 |
| 리스크 목록을 짜는 주체 | 에이전트(고무도장) | bot | **당신, 코드를 보기 전에** |
| 모든 주장이 `file:line` 인용 | 아니오 | 가끔 | **예 (schema 강제)** |
| citation을 디스크에서 재검증 | 아니오 | 아니오 | **예 (`lint`, 오프라인, 결정론적)** |
| *조작된* citation을 잡음 | 아니오 | 아니오 | **예 (run이 실패)** |
| 명확한 fabrication-rate 숫자 | 아니오 | 아니오 | **예 (`metrics`, 그걸로 게이트)** |
| PR이 게이트할 수 있는 기계 pass/fail | 아니오 | 부분적 | **예 (안정적 exit code)** |
| 영속적이고 재검증 가능한 artifact | 아니오 (chat 메시지) | review 코멘트 | **예 (markdown + JSON + scorecard)** |

그 채점 기준이 `antemortem`입니다 — 에이전트 자신의 확신이 아니라 프로그램이 검사합니다.

---

## 30초 만에 시험 — API key 불필요

번들 데모는 저장된 출력에서 실제 recon을 재생하므로 **key도 네트워크도** 필요 없습니다. 끝의 `lint`가 라이브 오프라인 검사입니다:

```bash
git clone https://github.com/hibou04-ops/antemortem-cli.git
cd antemortem-cli && pip install -e ".[mcp]"

# 4 traps → REAL / GHOST / NEW / UNRESOLVED → a decision (pre-recorded, offline)
PYTHONIOENCODING=utf-8 python examples/demo_replay.py

# now machine-verify every file:line and evidence hash against disk
antemortem lint examples/demo_antemortem.md --repo .

# ...and reduce it to one fabrication-rate number
antemortem metrics examples/demo_antemortem.json --repo .
```

`lint`는 모든 citation이 디스크에서 성립하면 `0`, 하나라도 조작/낡은 것이면 `1`로 종료합니다. 그 단 하나의 exit code가 제품 전부입니다: *"AI가 코드베이스에 대해 거짓말했는가?"*에 대한 결정론적·오프라인 답.

---

## 왜 작동하는가 — 두 가지 아이디어 ("antemortem"이라는 단어)

*post*-mortem은 이미 실패한 것의 이유를 묻습니다. **antemortem은 환자 — 당신의 변경 — 가 태어나기도 전에 부검을 합니다:** 첫 키 입력 *전에* AI의 계획을 실제 코드에 대해 심문합니다. 그 단어가 곧 방법론이고, 두 가지 메커니즘이 검토를 고무도장으로 만들 수 없게 합니다:

1. **Anchoring defense.** *당신이* 리스크("traps")를 **모델이 코드를 보기 전에** 열거합니다. 모델은 당신의 리스크 목록을 짜지 못하므로, 자기 프레임에 조용히 동의하고 그걸 검토라 부를 수 없습니다. 모델은 *당신의* 가설에 대해, *당신의* 파일 범위에 맞서 입장을 정해야 합니다.
2. **Hallucination-proof review.** `UNRESOLVED`가 아닌 모든 판단은 기계 검증 가능한 디스크 citation이며, **결정론적 오프라인 lint가 citation이 조작되면 run을 실패시킵니다.** artifact에 `evidence_hash`나 snippet이 있으면 lint는 인용된 *텍스트*가 드리프트하지 않았는지도 확인합니다. 모델의 확신은 무관합니다 — 디스크만이 결정합니다.

| Label | 의미 | 필요한 증거 |
|---|---|---|
| `REAL` | 코드가 리스크를 확인함. | 그것이 나타나는 `file:line` |
| `GHOST` | 코드가 그것을 반증함(이미 처리됨). | 그것에 반하는 `file:line` |
| `NEW` | 당신이 놓쳤지만 모델이 찾은 리스크. | 그것을 일으키는 코드의 `file:line` |
| `UNRESOLVED` | 어느 쪽 증거도 없음. 실패가 아니라 정직함. | 없음 (설명 필요) |

주류 도구 중 LLM 정찰을 이처럼 lint 가능·게이트 가능한 CI artifact로 바꾸는 것은 없습니다. 전체 trust model — 무엇을 검증하고 무엇을 의도적으로 검증하지 않는지 — 은 [`docs/trust_model.md`](docs/trust_model.md) ([한국어](docs/trust_model_kr.md))에 있습니다.

---

## 전체 루프 (API key 사용)

```bash
export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY / GEMINI_API_KEY / GOOGLE_API_KEY; Ollama needs no key

antemortem init    my-feature                          # scaffold the recon doc
#   edit antemortem/my-feature.md:
#     § Spec   — the change   § Traps — YOUR risk hypotheses   § Files — the scope
antemortem doctor  antemortem/my-feature.md --repo .   # preflight: no API call
antemortem run     antemortem/my-feature.md --repo .   # one call → classifications + citations
antemortem lint    antemortem/my-feature.md --repo .   # re-verify every citation offline
antemortem gate    antemortem/my-feature.md --repo .   # enforce the decision policy
antemortem metrics antemortem/my-feature.json --repo . # fabrication-rate number
antemortem report  antemortem/my-feature.json --repo . --format html --out scorecard.html
```

이것이 전체 명령 표면입니다 — **9 commands**: `init`, `doctor`, `run`, `lint`, `evidence`, `gate`, `eval`, `metrics`, `report`. `evidence`는 evidence hash를 채우거나 검사하고(provider 호출 없음), `eval`은 오프라인 golden case를 채점하며, `lint`의 `--strict-evidence`는 줄 범위뿐 아니라 인용된 *텍스트*가 변경되지 않았을 것을 요구합니다.

---

## 멀티 프로바이더 — 로컬·keyless Ollama 포함

방법론은 vendor-중립이며, LLM만이 교체 가능한 이음새입니다. **`anthropic`, `openai`, `gemini`, `ollama`**(실행 중인 daemon을 통한 로컬·keyless 추론)에 대한 first-class 어댑터를 제공하고, `--provider openai --base-url <url>`로 모든 **OpenAI-compatible endpoint**(Azure, Groq, Together, OpenRouter)를 지원합니다:

```bash
antemortem run antemortem/feat.md --repo . --provider ollama          # local, no API key
antemortem run antemortem/feat.md --repo . --provider openai --base-url https://...  # compatible endpoint
```

모든 어댑터는 provider의 native structured-output 경로를 사용하고 결과를 동일한 Pydantic schema로 검증합니다 — 어디에도 client-side JSON regex는 없습니다. CLI는 model-agnostic을 유지합니다. `--model`로 어떤 모델이든 고정하세요. 로컬·부분 호환 endpoint는 structured-output 충실도가 다양하므로 거기서는 `lint`가 필수로 유지됩니다 — 그것이 핵심입니다: 디스크 검사는 vendor와 무관하게 모델을 믿지 않습니다. 전체 capability matrix는 [`docs/provider_compatibility.md`](docs/provider_compatibility.md)에 있습니다.

---

## 언제 쓰지 말아야 하는가

사소한 변경(오타, 버전 bump), spec이 아직 없는 탐색적 spike, 속도가 규율을 이기는 hot-fix에는 antemortem을 건너뛰세요. 그것은 *기존 코드에 대한 계획*을 검증합니다 — 파일 밖에 사는 런타임 버그는 잡지 않습니다. 방향을 바꾸기가 가장 싼 지점에서 code review, 테스트, design review **전에** 실행되는 선별 게이트이지, 그것들의 대체물이 아닙니다. antemortem이 나머지 toolkit에 대해 어디에 위치하는지는 [`docs/toolkit_positioning.md`](docs/toolkit_positioning.md) ([한국어](docs/toolkit_positioning_kr.md))에 매핑되어 있습니다.

---

실제 엔지니어링 위에 구축됨: 오프라인 테스트 스위트(`python -m pytest -q`, 정상 CI에서 네트워크 0), MCP server, 네 개의 first-class provider, 결정론적 decision gate, 그리고 composite GitHub Action. 공개 주장 표면은 source에서 생성되고 self-check됩니다 — [`docs/generated/claims.md`](docs/generated/claims.md) ([한국어](docs/generated/claims_kr.md)) 참조, `python scripts/check_repo_consistency.py`로 검증됩니다.

```bash
pip install "antemortem[mcp]"      # MCP server + CLI
pip install antemortem             # CLI only
pip install "antemortem[ollama]"   # add local Ollama support
```

[`docs/`](docs/)의 심화 자료: CLI 레퍼런스 & exit code · trust model · GitHub Action · MCP 설정 · schema (`src/antemortem/schema.py`) · decision rules (`src/antemortem/decision.py`). 방법론 기원: [Antemortem](https://github.com/hibou04-ops/Antemortem).

License: Apache 2.0. © 2026 Kyunghoon Gwak.
