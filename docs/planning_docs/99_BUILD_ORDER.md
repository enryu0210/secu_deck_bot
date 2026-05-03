# 99. Build Order — Claude Code 단계별 작업 가이드

> **이 문서를 처음부터 순서대로 따라가세요. 각 단계의 체크리스트가 모두 통과해야 다음으로 넘어갑니다.**

---

## ⚠️ 시작 전 필수 — Phase 0: 보안 사전 작업

봇 코드 한 줄 작성하기 전에 **반드시** 완료할 것.

### 체크리스트

- [ ] **노출된 OpenAI API 키 무효화** — OpenAI 대시보드에서 즉시 revoke
- [ ] **노출된 모든 키 무효화** — Anthropic, Google, GitHub PAT 등
- [ ] **`.gitignore` 정비**
  ```
  .env
  .env.local
  .env.*.local
  *.key
  ```
- [ ] **Git 히스토리 클리닝**
  ```bash
  # BFG Repo-Cleaner 사용
  bfg --delete-files .env
  git reflog expire --expire=now --all
  git gc --prune=now --aggressive
  git push --force  # 팀에 사전 공지!
  ```
- [ ] **`.env.example` 커밋** (실제 값 X, 형식만)
- [ ] **새 키 발급**:
  - [ ] Anthropic API key
  - [ ] Google AI Studio API key (Gemini)
  - [ ] OpenAI API key
  - [ ] GitHub PAT (read-only, repo scope만)
- [ ] **Discord 봇 5개 등록** (Developer Portal):
  - [ ] Pitch Sharpener
  - [ ] Code Sentinel
  - [ ] Interview Companion
  - [ ] Design Echo
  - [ ] Argos Self-Audit
  - [ ] Chief of Staff (Phase 3에서)
- [ ] **각 봇을 Secu Deck 디스코드 서버에 초대**
- [ ] **Railway 프로젝트 생성** + GitHub 연결

이 단계가 끝나면 `STAGE_0_DONE.md` 파일을 루트에 만들어 통과 표시.

---

## 🧱 Stage 1: Infrastructure 구축

> **참조 문서**: `01_INFRASTRUCTURE.md`
> **예상 시간**: 1~2일

### 작업 순서

1. **모노레포 초기화**
   ```bash
   mkdir secu-deck-bots && cd secu-deck-bots
   git init
   uv init --no-readme
   ```
   - `pyproject.toml`을 워크스페이스 모드로 설정 (`01_INFRASTRUCTURE.md` § 2)

2. **`packages/core` 스캐폴드**
   ```bash
   mkdir -p packages/core/src/sd_core/{llm,discord,personas,context,tracking,storage,utils}
   cd packages/core && uv init --package
   ```

3. **각 모듈 구현 순서**:
   - `utils/logger.py` (다른 모듈이 의존)
   - `utils/errors.py`
   - `llm/types.py` (LLMRequest, LLMResponse, TaskType)
   - `llm/claude.py` (Anthropic 어댑터, **Prompt Caching 필수**)
   - `llm/gemini.py`
   - `llm/openai.py`
   - `tracking/cost.py` (가격표 + 비용 계산)
   - `tracking/usage.py` (사용자 쿼터)
   - `llm/router.py` (모든 어댑터 통합 + cost·usage 적용)
   - `context/argos.py` (Argos_Context.md 로더 + mtime 감지)
   - `personas/base.py`, `personas/loader.py`
   - `discord/base_bot.py`, `discord/ui.py`
   - `storage/postgres.py` (Phase 2부터 사용)

4. **`shared/argos_context/Argos_Context.md` 배치**
   - 사용자가 제공한 `Argos_Context.md`를 이 위치에 복사

5. **단위 테스트**
   - 각 모듈 마다 최소 1개 테스트
   - LLMRouter는 mock 어댑터로 테스트

### Stage 1 완료 조건

- [ ] `uv sync` 성공
- [ ] `uv run pytest packages/core/tests` 모두 통과
- [ ] `from sd_core.llm.router import LLMRouter` import 성공
- [ ] `ArgosContext().get_summary()` 정상 동작 (실제 파일로)
- [ ] `PersonaLoader().load(...)` YAML 파싱 정상

---

## 🎤 Stage 2: Pitch Sharpener (Phase 1A)

> **참조 문서**: `02_PITCH_SHARPENER.md`
> **예상 시간**: 3~5일
> **목표**: 5월 사업계획서 재지원 D-day 전 가동

### 작업 순서

1. **봇 디렉토리 생성**
   ```bash
   mkdir -p bots/pitch_sharpener/{personas,prompts,src/pitch_sharpener}
   cd bots/pitch_sharpener && uv init --package
   ```

2. **6개 페르소나 YAML 작성**
   - `02_PITCH_SHARPENER.md` 부록의 2개(`customer_voice`, `data_skeptic`) 그대로 사용
   - 나머지 4개를 동일 구조로 작성:
     - `pricing_analyst.yaml`
     - `competitor_hunter.yaml`
     - `tech_differentiator.yaml`
     - `budget_reality.yaml`
   - 각 페르소나에 1차 탈락 원인 1개씩 매핑

3. **프롬프트 템플릿 작성**
   - `prompts/system_base.md` — 공통 베이스
   - `prompts/synthesizer.md` — 종합 단계
   - `prompts/quick_diagnosis.md` — 빠른 진단

4. **모듈 구현 순서**:
   - `document_parser.py` — PDF/MD/DOCX 파싱
   - `persona_runner.py` — 단일 페르소나 호출
   - `synthesizer.py` — 종합
   - `review_engine.py` — 오케스트레이션 (병렬 호출)
   - `ui.py` — Discord 임베드·버튼
   - `commands.py` — 슬래시 커맨드 3종
   - `main.py` — 봇 엔트리

5. **테스트**
   - 짧은 더미 사업계획서로 풀 리뷰
   - 1차 탈락한 실제 사업계획서로 평가 (6/6 원인 정확히 짚는지)

6. **Dockerfile + railway.toml**
   - `01_INFRASTRUCTURE.md` § 4, § 5 템플릿 사용

7. **Railway 배포**
   - 환경변수 설정
   - `main` 브랜치 push → 자동 빌드
   - 디스코드에서 `/pitch quick` 시도

### Stage 2 완료 조건

`02_PITCH_SHARPENER.md` § 완료 체크리스트 전체

---

## 💻 Stage 3: Code Sentinel (Phase 1B)

> **참조 문서**: `03_CODE_SENTINEL.md`
> **예상 시간**: 3~5일

### 작업 순서

1. **봇 디렉토리 생성** (Stage 2와 동일 패턴)

2. **룰 YAML 작성**
   - `rules/argos_patterns.yaml` — 알려진 안티패턴 10개 이상
   - `rules/kisa_guidelines.yaml` — 핵심 가이드라인
   - `rules/pipa_articles.yaml` — 개인정보보호법 주요 조항

3. **모듈 구현 순서**:
   - `language_detector.py` — 코드 언어 판별
   - `rule_matcher.py` — 룰베이스 1차 검사
   - `escalator.py` — 모델 자동 승급 판단
   - `github_fetcher.py` — PR URL 처리
   - `reviewer.py` — 리뷰 메인
   - `ui.py`, `commands.py`, `main.py`

4. **테스트**
   - Argos 실제 PR 5개로 통합 테스트
   - 보안 이슈 누락 0건 확인

5. **배포**

### Stage 3 완료 조건

`03_CODE_SENTINEL.md` § 완료 체크리스트 전체

---

## 🎙 Stage 4: Interview Companion + 🎨 Design Echo (Phase 2 병행)

> **참조 문서**: `04_INTERVIEW_COMPANION.md`, `05_DESIGN_ECHO.md`
> **예상 시간**: 5~7일 (병행)

이 두 봇은 사용자가 다르고 의존성이 적어 **병행 가능**. 다만 Postgres 의존성이 있으니 먼저:

1. **Railway에 Postgres 추가**
2. **`packages/core/storage/postgres.py` 활성화·테스트**
3. **마이그레이션 적용**:
   - `interview_companion`용 테이블
   - `cost_tracker`용 `llm_calls` 테이블 (이미 Stage 1에서 생성)

그 다음 두 봇 병행:

### Interview Companion 작업

1. `data/argos_hypotheses.yaml` 작성 (가설 4~6개)
2. 모듈 구현:
   - `storage.py`
   - `interview_prep.py`
   - `interview_logger.py`
   - `insight_extractor.py`
   - `commands.py`, `main.py`
3. 테스트: 인터뷰 더미 데이터 5건으로 누적 분석
4. 배포

### Design Echo 작업

1. **디자인팀과 함께** `design_system/` YAML 3개 작성:
   - `tokens.yaml`
   - `components.yaml`
   - `tone_guide.yaml`
2. 모듈 구현:
   - `consistency_checker.py`
   - `spec_generator.py`
   - `copy_reviewer.py`
   - `commands.py`, `main.py`
3. 테스트: PNG 시안 5개로 토큰 추출·비교
4. 배포

### Stage 4 완료 조건

각 문서의 완료 체크리스트.

---

## 🏛 Stage 5: Chief of Staff Phase 3 — 라우팅 모드

> **참조 문서**: `06_CHIEF_OF_STAFF.md` § Phase 3
> **예상 시간**: 4~5일
> **전제**: Stage 2~4 안정 가동 1주일 이상

### 작업 순서

1. **각 봇에 `/api/invoke` 엔드포인트 추가**
   - 5개 봇 모두에 FastAPI 추가
   - 공유 시크릿 환경변수 설정 (`INTERNAL_API_SECRET`)
   - Railway에서 각 봇 서비스의 내부 URL 확인

2. **Chief of Staff 봇 디렉토리**
   ```bash
   mkdir -p bots/chief_of_staff/src/chief_of_staff
   ```

3. **모듈 구현**:
   - `intent_router.py` — Haiku 의도 분류
   - `delegator.py` — HTTP 호출로 봇 위임
   - `synthesizer.py` — 봇 응답을 cos 스타일로 포장
   - `commands.py`, `main.py`

4. **메시지 리스너**
   - `@cos` 멘션 감지 → 의도 분류 → 위임
   - 슬래시 커맨드 `/council` (Phase 5 placeholder)

5. **테스트**
   - 50개 테스트 메시지로 의도 분류 정확도 측정
   - 5개 봇 모두 위임 성공 확인

6. **배포**

### Stage 5 완료 조건

`06_CHIEF_OF_STAFF.md` § Phase 3 완료 체크리스트.

---

## 🛡 Stage 6: Argos Self-Audit (Phase 4)

> **참조 문서**: `07_ARGOS_SELF_AUDIT.md`
> **예상 시간**: 2~3일

### 작업 순서

1. **봇 디렉토리 생성**

2. **체크 룰 YAML 작성**:
   - `checks/secret_patterns.yaml`
   - `checks/pii_patterns.yaml`
   - `checks/kisa_checks.yaml`
   - `checks/pipa_articles.yaml`

3. **모듈 구현**:
   - `repo_scanner.py` — 룰베이스 스캔 (LLM 없이)
   - `dependency_checker.py` — CVE 체크 (osv-scanner 활용)
   - `compliance_mapper.py` — PRD → 법령 매핑
   - `github_webhook.py` — FastAPI webhook
   - `scheduler.py` — discord.py tasks
   - `reporter.py` — 디스코드 임베드 생성
   - `commands.py`, `main.py`

4. **GitHub Webhook 설정**
   - Argos repo Settings → Webhooks → 추가
   - URL: Railway에서 노출된 webhook URL
   - Secret: 안전한 랜덤값
   - Events: pull_request

5. **`#self-audit` 채널 생성·권한 설정**

6. **테스트**:
   - 즉시 스캔 실행 (`/audit scan`)
   - 더미 PR 생성·머지 → webhook 동작 확인
   - PRD 더미로 컴플라이언스 매핑

7. **배포**

### Stage 6 완료 조건

`07_ARGOS_SELF_AUDIT.md` § 완료 체크리스트.

---

## 🟣 Stage 7 (선택): Chief of Staff Phase 5 — Council 모드

> **참조 문서**: `06_CHIEF_OF_STAFF.md` § Phase 5
> **예상 시간**: 7~10일
> **전제**: Stage 1~6 안정 가동 1개월 이상, 10월 출시 후 안정기

이건 정말 도전적인 작업. 시간·비용 여유 있을 때만 시작 권장.

### 작업 순서

1. **LangGraph 학습·도입**
2. **워크플로우 그래프 구현**
3. **발언권 알고리즘**
4. **종료 조건 (3종)**
5. **Postgres에 회의 기록 저장 (페르소나 일관성용)**
6. **`/council` 커맨드만 활성화** (`@cos` 멘션으로는 트리거 X)
7. **풀 카운슬 테스트 (예산 주의)**

---

## 📋 통합 마일스톤

| 시점 | 마일스톤 | 가동 봇 |
|---|---|---|
| 4월 말 | Stage 0~2 완료 | Pitch Sharpener |
| 5월 말 | Stage 3 완료 | + Code Sentinel |
| 7월 초 | Stage 4 완료 | + Interview, Design (5봇 모두) |
| 8월 | Stage 5 완료 | + Chief of Staff (라우팅) |
| 9월 | Stage 6 완료 | + Argos Self-Audit |
| 11월~ | Stage 7 (선택) | + Council 모드 |

---

## 🔄 빌드 중 자주 마주칠 이슈

### 이슈 1: Anthropic Rate Limit
- 증상: 6 페르소나 병렬 호출 시 429 에러
- 대응: `asyncio.Semaphore(3)` 동시성 제한, 또는 단계적 호출

### 이슈 2: Prompt Caching 적용 안 됨
- 확인: `response.usage.cache_read_input_tokens` 값 0이면 캐시 미적용
- 원인: 시스템 프롬프트가 너무 짧음 (1024 토큰 미만은 캐시 안 됨), 또는 `cache_control` 누락
- 대응: Argos 컨텍스트 길이 확인, `cache_control: {"type": "ephemeral"}` 추가

### 이슈 3: Railway 빌드 시간 초과
- 모노레포라 빌드 컨텍스트가 큼
- 대응: `.dockerignore`로 불필요 디렉토리 제외, watch paths로 봇별 트리거 분리

### 이슈 4: Discord 슬래시 커맨드 동기화 지연
- 글로벌 동기화는 최대 1시간 걸릴 수 있음
- 개발 중에는 길드 동기화 사용: `bot.tree.sync(guild=Object(id=GUILD_ID))`

### 이슈 5: 비용 예상 초과
- Stage별 1주일 dry-run 후 실측
- 초과 시 router.py의 모델 매핑 조정 (Sonnet → Haiku)

---

## 📞 참조

- `00_OVERVIEW.md` — 전체 그림
- `01_INFRASTRUCTURE.md` — 코어 인프라
- `02~07_*.md` — 봇별 빌드 가이드
- `Argos_Context.md` — 제품 컨텍스트 (별도 제공)

각 Stage 완료 시 봇 작동 영상·스크린샷을 디스코드 채널에 공유 권장. 팀이 빌드 진행 상황을 볼 수 있어야 함.
