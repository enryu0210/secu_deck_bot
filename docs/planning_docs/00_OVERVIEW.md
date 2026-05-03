# Secu Deck Discord Bots — Overview

> **목적**: Argos(AI 보안 컴플라이언스 B2B SaaS) 개발을 가속하는 Discord 봇 생태계 구축
> **팀**: Secu Deck (대표 1, 개발 3, 디자인 2, 총 6명)
> **호스팅**: Railway (봇별 별도 서비스)
> **예산**: 월 200,000원 (API + Railway 합산)

---

## 🎯 빌드 대상

총 5개 봇 + 1개 메타봇(Phase 3) + 공통 코어 패키지.

| Phase | 봇 | 주 사용자 | 모델 | 우선순위 |
|---|---|---|---|---|
| **1A** | 🎤 Pitch Sharpener | 대표 | Claude Sonnet 4.5 | ★★★★★ (5월 D-day) |
| **1B** | 💻 Code Sentinel | 개발 3명 | Claude Haiku 4.5 + Sonnet 폴백 | ★★★★☆ |
| **2** | 🎙 Interview Companion | 대표 | Gemini 2.5 Flash + Claude Sonnet | ★★★☆☆ |
| **2** | 🎨 Design Echo | 디자인 2명 | Gemini 2.5 Flash (vision) | ★★★☆☆ |
| **3** | 🏛 Chief of Staff (메타) | 전원 | Claude Sonnet 4.5 | ★★☆☆☆ |
| **4** | 🛡 Argos Self-Audit | 전원 | Claude Sonnet 4.5 | ★★☆☆☆ |

---

## 🧱 공통 아키텍처 원칙

### 1. 모노레포 + 봇별 독립 배포

```
secu-deck-bots/
├── packages/core/           # 모든 봇이 공유 (sd_core)
├── bots/
│   ├── pitch_sharpener/    # 각 봇 = Railway 독립 서비스
│   ├── code_sentinel/
│   ├── interview_companion/
│   ├── design_echo/
│   ├── chief_of_staff/     # Phase 3
│   └── argos_self_audit/   # Phase 4
└── docs/
```

**원칙**: 봇 하나 죽어도 다른 봇은 살아있어야 함. `packages/core`만 공유.

### 2. LLM 라우팅 의무화

모든 봇은 **`sd_core.llm.router.LLMRouter`만** 통해 모델 호출. 직접 `anthropic.Anthropic()` 호출 금지.
이유:
- 비용 추적 (cost_tracker)
- 모델 폴백 (Haiku → Sonnet 자동 승급)
- 프롬프트 캐싱 일관 적용
- 추후 모델 교체 시 한 곳만 수정

### 3. Argos 컨텍스트 항상 캐시

`Argos_Context.md`는 모든 봇의 시스템 프롬프트에 들어감. 매번 로드하면 비용 폭발.
→ **Anthropic Prompt Caching** 사용 (5분 이상 호출 시 재사용, 75~90% 비용 절감).

### 4. 비용 가드레일

각 봇은 다음을 강제:
- 사용자별 일일 호출 횟수 상한 (config로 정의)
- 응답 max_tokens 보수적 설정
- Cost Tracker가 월 한도 90% 도달 시 봇이 사용자에게 경고
- 100% 도달 시 비핵심 기능 자동 차단

### 5. 실패 시 사람에게 솔직하게

LLM이 답을 못 내거나 모를 때, 가짜 답 생성 금지. "지금 답을 만들 자신이 없어요. 더 구체적인 정보를 주실 수 있나요?" 식으로 응답.

---

## 🔐 Phase 0: 보안 사전 작업 (봇 빌드 전 필수)

봇 빌드 시작 전 **반드시** 완료:

1. **노출된 API 키 무효화** — OpenAI 대시보드에서 즉시 revoke
2. **`.gitignore` 정비** — `.env`, `.env.local` 추가
3. **Git 히스토리 클리닝** — `bfg --delete-files .env` 실행 후 force push
4. **`.env.example` 커밋** — 키 형식만, 실제 값 X
5. **Discord Developer Portal**에서 봇별 토큰 발급 (5개)
6. **Railway 프로젝트 생성**, GitHub 연결

이 작업이 끝났는지 `99_BUILD_ORDER.md`의 체크리스트로 확인 후 진행.

---

## 🛠 기술 스택 (확정)

| 영역 | 선택 | 비고 |
|---|---|---|
| 언어 | Python 3.12 | |
| 패키지 매니저 | uv | workspace 모드 |
| Discord 라이브러리 | discord.py 2.4+ | |
| LLM SDK | anthropic, google-genai, openai | 직접 사용 (래퍼 X) |
| 에이전트 프레임워크 (Phase 3+) | LangGraph | Council 모드 시작 시 |
| DB | Railway Postgres + pgvector | 인터뷰·회의 메모리 |
| 관측성 | Langfuse self-host (또는 자체 로깅) | Phase 2부터 도입 권장 |
| 배포 | Railway, Dockerfile 기반 | 봇별 독립 서비스 |

---

## 📊 모델 선택 가이드

각 봇이 어떤 모델을 왜 쓰는지 한눈에:

| 작업 유형 | 1순위 | 2순위 (폴백) | 이유 |
|---|---|---|---|
| 사업계획서 글쓰기·리뷰 | Claude Sonnet 4.5 | Claude Opus 4.5 | 한국어 글쓰기·구조화 강함 |
| 코드 리뷰 (간단) | Claude Haiku 4.5 | Claude Sonnet 4.5 | 빠르고 저렴, 코드 이해 우수 |
| 코드 리뷰 (복잡, 보안) | Claude Sonnet 4.5 | — | 추론력 필요 |
| 이미지 이해 (디자인) | Gemini 2.5 Flash | Claude Sonnet 4.5 | 가성비 압도적, 멀티모달 강함 |
| 대용량 컨텍스트 (인터뷰 누적) | Gemini 2.5 Flash | Gemini 2.5 Pro | 1M 토큰 컨텍스트 |
| 인사이트 추출·종합 | Claude Sonnet 4.5 | — | 한국어 분석 품질 |
| 단순 라우팅·분류 | Claude Haiku 4.5 | GPT-4.1 mini | 저비용 |

> **주의**: 위 모델명은 2026.04 기준. 실제 빌드 시 각 공급자 문서에서 최신 모델 ID·가격 확인 필수.
> Anthropic: https://docs.claude.com/en/docs/about-claude/models
> Google: https://ai.google.dev/gemini-api/docs/models
> OpenAI: https://platform.openai.com/docs/models

---

## 📁 빌드 순서

상세는 `99_BUILD_ORDER.md` 참조. 요약:

1. **Phase 0 보안 작업** (반나절)
2. **`packages/core` 구축** (1~2일) — `01_INFRASTRUCTURE.md`
3. **Pitch Sharpener** (3~5일) — `02_PITCH_SHARPENER.md`
4. **Code Sentinel** (3~5일) — `03_CODE_SENTINEL.md`
5. **Interview Companion + Design Echo 병행** (5~7일) — `04`, `05`
6. **Chief of Staff (메타)** (3~4일) — `06_CHIEF_OF_STAFF.md`
7. **Argos Self-Audit** (2~3일) — `07_ARGOS_SELF_AUDIT.md`

---

## 📚 참조 문서

- `Argos_Context.md` — Argos 제품 상세 (별도 제공)
- `01_INFRASTRUCTURE.md` — 모노레포·core·Railway 배포
- `02_PITCH_SHARPENER.md` ~ `07_ARGOS_SELF_AUDIT.md` — 봇별 빌드 가이드
- `99_BUILD_ORDER.md` — Claude Code가 따라갈 단계별 작업 지시
