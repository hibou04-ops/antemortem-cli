# antemortem (CLI) — 쉬운 설명

> 본 README가 어렵게 느껴지는 분들을 위한 압축 버전.
> 원본: [README_KR.md](README_KR.md) · English easy: [EASY_README.md](EASY_README.md)

## 이게 뭔가요?

[Antemortem methodology](https://github.com/hibou04-ops/Antemortem)를 대신 실행해주는 3-커맨드 CLI — 리스크 doc scaffold, 실제 코드에 대해 트랩 분류 (structured output LLM 호출), 인용이 신뢰할 만한지 lint.

변경 1건당 15분. CI에서 gate 걸 수 있는 machine-readable artifact 생성.

## 3 커맨드가 API 전부

```bash
# 1. 템플릿에서 markdown doc scaffold
antemortem init auth-refactor
# → antemortem/auth-refactor.md  (Spec + Traps + Files 섹션 편집)

# 2. LLM 분류 실행
antemortem run antemortem/auth-refactor.md --repo .
# → antemortem/auth-refactor.json  (REAL/GHOST/NEW/UNRESOLVED + file:line + decision)

# 3. Lint (모든 file:line 인용이 디스크에 실제 존재하는지 확인)
antemortem lint antemortem/auth-refactor.md --repo .
# Exit 0 = 신뢰 가능; Exit 1 = 인용이 거짓
```

선택적 4번째 형태: `antemortem run ... --critic` — 2차 adversarial pass. **다운그레이드만** 가능 (CONFIRMED / WEAKENED / CONTRADICTED / DUPLICATE). 비용 ~2배. LLM 과잉 확신 잡아냄.

## 설치

```bash
pip install antemortem
```

PyPI 이름은 `antemortem` (not `antemortem-cli`). Python 3.11+.

## API 키

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # --provider anthropic용 (기본: claude-opus-4-7)
export OPENAI_API_KEY=sk-...            # --provider openai용     (기본: gpt-4o)
```

OpenAI-호환 엔드포인트 (Azure, Groq, Together, OpenRouter, Ollama) 는:
```bash
antemortem run foo.md --repo . --provider openai --base-url https://... --model ...
```

## 리턴되는 것

JSON artifact 4부분:

1. **Classifications** — 당신이 리스트한 트랩 하나당 하나. `REAL` (코드가 확인), `GHOST` (코드가 반박), `NEW` (LLM이 발견), `UNRESOLVED` (증거 없음). 각각 `file:line` 인용 + 1–2 문장 note + 선택적 severity + remediation.
2. **New traps** — LLM이 발견했지만 당신이 리스트 안 한 리스크.
3. **Spec mutations** — recon이 권장하는 스펙 수정 사항.
4. **Decision gate** — 네 가지 중 하나:
   - `SAFE_TO_PROCEED` — REAL 없음
   - `PROCEED_WITH_GUARDS` — REAL 있지만 전부 remediation 있음
   - `NEEDS_MORE_EVIDENCE` — UNRESOLVED ≥50%, 또는 REAL인데 remediation 빠짐
   - `DO_NOT_PROCEED` — high-severity REAL/NEW 중 remediation 없는 것, 또는 critic이 finding 반박

CI는 enum에 gate. 사람은 rationale 읽음.

## 정직하게 만드는 가드레일 2개

- **LLM이 코드 보기 *전에* 당신이 트랩을 나열한다.** 템플릿 강제. LLM이 리스크 리스트를 frame 못 하게.
- **모든 분류는 `file:line` 인용 필수.** SDK 경계에서 Pydantic 강제. `antemortem lint`가 모든 인용을 디스크 line count와 대조 — hallucinated 범위는 빌드 실패.

둘 중 하나라도 없으면 그냥 Claude에 vibe-check 부탁한 것. 둘 다 있으면 15분 기계적 screening.

## 쓰면 안 되는 경우

- 사소한 변경 (오타, 한 줄 config, docstring).
- 스펙 아직 없음 — 스펙 먼저 쓰고 *그 다음* antemortem.
- 코드에 몇 달 살아서 답을 이미 암.
- 빌드 시간 < recon 시간.

## 1분 데모

```bash
antemortem init my-change
# antemortem/my-change.md 편집:
#   - "Spec" 섹션 채우기
#   - Traps 테이블에 최소 1행 추가
#   - "Recon protocol" 아래 최소 1개 파일 listing

antemortem run antemortem/my-change.md --repo .
# 나열된 파일을 repo에서 읽고 각 트랩 분류.

antemortem lint antemortem/my-change.md --repo .
# 모든 file:line 디스크 재검증. Exit 0 = 리포트 신뢰 가능.
```

## 더 깊이

- 전체 CLI 문서 + 플래그: [README_KR.md](README_KR.md)
- Methodology 본체 (이 CLI는 wrapper): [Antemortem repo](https://github.com/hibou04-ops/Antemortem)
- Schema 정의: `src/antemortem/schema.py`
- Decision gate 규칙: `src/antemortem/decision.py`

License: Apache 2.0. Copyright (c) 2026 hibou.
