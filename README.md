# Secu Deck Bots

> Argos(AI 보안 컴플라이언스 B2B SaaS) 개발을 가속하는 Discord 봇 모노레포.

## 구조

```
secu-deck-bots/
├── packages/core/              # sd-core: 모든 봇이 공유 (LLM 라우팅·페르소나·비용 추적)
├── bots/
│   ├── pitch_sharpener/        # 사업계획서 6 페르소나 리뷰 (Phase 1A)
│   ├── code_sentinel/          # 코드 리뷰 + KISA 정합성 (Phase 1B)
│   ├── interview_companion/    # 고객 인터뷰 가이드·기록 (Phase 2)
│   ├── design_echo/            # 디자인 일관성 + UX 라이팅 (Phase 2)
│   ├── chief_of_staff/         # 라우팅 메타봇 (Phase 3)
│   └── argos_self_audit/       # 자가 검증 (Phase 4)
├── shared/argos_context/       # Argos_Context.md 배치 위치
├── docs/planning_docs/         # 빌드 계획 문서
└── pyproject.toml              # uv 워크스페이스 루트
```

## Phase 0 — 봇 코드 작성 전 필수 작업

`docs/planning_docs/99_BUILD_ORDER.md` 의 Phase 0 체크리스트 참고. 요약:

1. 노출된 API 키 무효화 (OpenAI/Anthropic/Google/GitHub)
2. 새 키 발급 후 `.env` 에 저장 (`.env.example` 참조)
3. Discord Developer Portal 에서 봇 5개 등록·서버 초대
4. Railway 프로젝트 생성·GitHub 연결
5. `shared/argos_context/Argos_Context.md` 배치
6. 완료 후 `STAGE_0_DONE.md` 루트에 생성

## 로컬 개발

```bash
# 워크스페이스 install
uv sync

# 봇 실행 (예: Pitch Sharpener)
cd bots/pitch_sharpener
uv run python -m pitch_sharpener.main

# 코어 테스트
uv run pytest packages/core/tests
```

## 주의

- 모든 LLM 호출은 `sd_core.llm.router.LLMRouter` 만 사용 (직접 SDK 호출 금지).
- Argos 컨텍스트는 자동 캐싱 적용. `cache_control` 수동 설정 불필요.
- 코드/이미지가 외부 LLM API 로 전송됨. 민감 정보는 봇 사용 전 마스킹 필요.
- 모델 ID(`claude-sonnet-4-5` 등)는 2026.04 추정. 실 배포 시 각 공급자 문서로 검증.

## 참조 문서

- `docs/planning_docs/00_OVERVIEW.md` — 전체 아키텍처
- `docs/planning_docs/01_INFRASTRUCTURE.md` — 코어 인프라 상세
- `docs/planning_docs/99_BUILD_ORDER.md` — 단계별 빌드 가이드
