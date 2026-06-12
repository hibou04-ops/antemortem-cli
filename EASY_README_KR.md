# antemortem — 쉬운 시작

> 메인 README가 부담스러웠던 분들을 위한 짧은 버전.

[![PyPI](https://img.shields.io/pypi/v/antemortem?color=blue&label=pypi&cacheSeconds=3600)](https://pypi.org/project/antemortem/)

README family: [English](README.md) · [한국어](README_KR.md) · [Easy](EASY_README.md) · [쉬운 한국어](EASY_README_KR.md)
Deep docs: generated claims [English](docs/generated/claims.md) · [한국어](docs/generated/claims_kr.md) · trust model [English](docs/trust_model.md) · [한국어](docs/trust_model_kr.md) · toolkit positioning [English](docs/toolkit_positioning.md) · [한국어](docs/toolkit_positioning_kr.md) · claim ledger [English](docs/claim_ledger.md) · [한국어](docs/claim_ledger_kr.md)

## 이게 뭔가요?

당신의 AI 코딩 에이전트는 계획을 써놓고 repo에 안전하다고 말합니다. 에이전트가 실제로 코드를 읽었는지, 아니면 그냥 자신 있게 말한 것뿐인지 빠르게 알 방법이 없습니다. `antemortem`이 바로 그 검사입니다.

당신은 걱정되는 리스크를 적습니다. 모델은 각 리스크를 당신의 실제 파일에 대해 분류하고, 모든 답에 `file:line`을 인용해야 합니다. 그다음 별도의 오프라인 단계가 인용된 각 줄을 디스크에서 다시 읽습니다. citation이 지어낸 것이면 검사가 — 요란하게 — 실패합니다. 모델의 확신은 아무것도 결정하지 않습니다. 디스크가 결정합니다.

이름이 곧 방법입니다. *post*-mortem(사후 부검)은 이미 깨진 것의 이유를 묻습니다. *antemortem*은 당신의 변경이 작성되기도 *전에* 부검을 합니다 — 계획에 대해, 아직 방향을 바꾸기 싼 동안에.

## 설치

```bash
pip install antemortem
```

PyPI 이름은 `antemortem`입니다(`antemortem-cli` 아님). Python 3.11+.

## 30초 만에 시험 — API key 불필요

번들 데모는 저장된 출력에서 실제 recon을 재생하므로 key도 네트워크도 필요 없습니다. 끝의 `lint`가 진짜 오프라인 검사입니다:

```bash
git clone https://github.com/hibou04-ops/antemortem-cli.git
cd antemortem-cli && pip install -e ".[mcp]"

# 4 risks → REAL / GHOST / NEW / UNRESOLVED → a decision (pre-recorded, offline)
PYTHONIOENCODING=utf-8 python examples/demo_replay.py

# now machine-verify every file:line and evidence hash against disk
antemortem lint examples/demo_antemortem.md --repo .
```

`lint`는 모든 citation이 디스크에서 성립하면 `0`, 하나라도 조작/낡은 것이면 `1`로 종료합니다. 그 단 하나의 exit code가 전부입니다: "AI가 코드베이스에 대해 거짓말했는가?"에 대한 결정론적·오프라인 답.

## 명령들

명령은 **9 commands**입니다. 시작할 때는 몇 개만 필요하고, 나머지는 CI와 리포팅용입니다.

- `antemortem init <name>` — 템플릿에서 recon 문서를 만듭니다. spec, 리스크("traps"), 검사할 파일을 채웁니다.
- `antemortem doctor <doc>` — preflight: 무엇이 읽히고 보내질지 보여줍니다, API 호출 없음.
- `antemortem run <doc>` — provider 호출 1회. 각 리스크를 `REAL` / `GHOST` / `NEW` / `UNRESOLVED`로 `file:line` citation과 함께 분류하고 JSON artifact를 씁니다.
- `antemortem lint <doc>` — 모든 citation을 디스크에 대해 오프라인으로 재검증합니다. 이것이 정직성 검사입니다.
- `antemortem evidence <artifact>` — 기존 artifact의 evidence hash를 채우거나 검사합니다, provider 호출 없음.
- `antemortem gate <doc>` — `lint`를 실행한 뒤 decision allowlist를 강제합니다. CI에 넣는 것이 이것입니다.
- `antemortem eval <cases>` — 오프라인 golden benchmark case를 채점합니다.
- `antemortem metrics <artifact>` — 모델이 실제 증거를 얼마나 인용했고 얼마나 조작했는지 출력합니다: verified / fabricated 수와 fabrication rate. `--fail-over 0`을 더하면 지어낸 citation이 하나라도 있으면 CI 실패.
- `antemortem report <artifact>` — run을 PR에 첨부 가능한 Markdown 또는 HTML scorecard로 렌더링합니다.

전형적인 첫 실행:

```bash
antemortem init my-change
# edit antemortem/my-change.md: the Spec, your Traps, and the Files to read
antemortem doctor antemortem/my-change.md --repo .
antemortem run    antemortem/my-change.md --repo .
antemortem lint   antemortem/my-change.md --repo .
antemortem gate   antemortem/my-change.md --repo .
```

## 결정의 의미

모든 run은 네 verdict 중 하나로 끝나며, CI가 그것으로 분기할 수 있습니다:

- `SAFE_TO_PROCEED` — 남은 실제 리스크 없음.
- `PROCEED_WITH_GUARDS` — 실제 리스크가 있으나 각각 remediation 있음.
- `NEEDS_MORE_EVIDENCE` — unresolved가 너무 많거나 citation이 성립하지 않음.
- `DO_NOT_PROCEED` — mitigation 없는 high-severity 리스크.

exit code는 안정적입니다: `0` pass, `1` validation/citation 실패, `2` usage error, `3` provider 실패, `4` policy gate 차단(`70`은 internal error용 예약).

## Providers

`anthropic`, `openai`, `gemini`, `ollama`에 대한 어댑터를 제공합니다. Ollama는 로컬에서 실행되며 **API key가 필요 없습니다** — 가입 없이 써보기 좋습니다:

```bash
export ANTHROPIC_API_KEY=sk-ant-...                  # or OPENAI_API_KEY / GEMINI_API_KEY
antemortem run antemortem/my-change.md --repo . --provider ollama   # local, no key
```

CLI는 model-agnostic입니다 — `--model`로 어떤 모델이든 고정하세요. 모든 OpenAI-compatible endpoint는 `--provider openai --base-url <url>`로 작동합니다.

## 에이전트가 자기 작업을 검사하게 하기

`antemortem-mcp`를 실행하면 AI 어시스턴트(Claude Code, Cursor)가 merge를 요청하기 전에 자기 계획에 대해 `scaffold` / `run` / `lint`를 호출할 수 있습니다. 설정은 config 한 번 붙여넣기 — 자세한 내용은 [docs/MCP.md](docs/MCP.md)를 보세요.

그리고 citation이 성립하지 않을 때 pull request를 실패시키려면 CI에 한 줄 — `antemortem gate ...` — 을 추가하거나, 번들 GitHub Action을 사용하세요. [docs/GITHUB_ACTION.md](docs/GITHUB_ACTION.md)를 보세요.

## 이걸 정직하게 만드는 두 가드레일

- **모델이 코드를 보기 전에 당신이 리스크를 적습니다.** 모델은 당신의 리스크 목록을 짤 수 없으므로, 자기 자신에게 조용히 동의하고 그걸 검토라 부를 수 없습니다.
- **모든 답은 `file:line` citation을 달고, 디스크에서 재확인됩니다.** 조작된 citation은 run을 실패시킵니다. 모델의 확신은 무관합니다 — 디스크만이 결정합니다.

에이전트에게 자기 계획을 검토하라고 하는 것에는 채점 기준이 없습니다. antemortem이 그 채점 기준이며, 프로그램이 검사합니다.

## 언제 쓰지 말아야 하는가

- 사소한 변경(오타, 한 줄 config, 버전 bump).
- spec이 아직 없음 — spec을 먼저 쓰고, 그다음 antemortem 하세요.
- 속도가 규율을 이기는 hot-fix, 또는 이미 훤히 아는 코드.

그것은 *기존 코드에 대한 계획*을 검증합니다 — 파일 밖의 런타임 버그는 잡지 않고, code review·테스트·design review를 대체하지 않습니다. 그것들 *전에* 실행되는 싼 선별 단계입니다. 더 넓은 toolkit에서의 위치는 [docs/toolkit_positioning.md](docs/toolkit_positioning.md) ([한국어](docs/toolkit_positioning_kr.md))에 매핑되어 있습니다.

## 더 깊이

- 전체 front page와 모든 flag: [README.md](README.md)
- 무엇을 검증하고 무엇을 안 하는지: [docs/trust_model.md](docs/trust_model.md) ([한국어](docs/trust_model_kr.md))
- 이 CLI가 감싸는 방법론: [Antemortem](https://github.com/hibou04-ops/Antemortem)

License: Apache 2.0. Copyright (c) 2026 Kyunghoon Gwak.
