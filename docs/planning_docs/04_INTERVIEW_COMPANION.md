# 04. Interview Companion — 고객 인터뷰 가이드·정리·인사이트 봇

> **Phase**: 2
> **주 사용자**: 대표 (1인, 영업·고객 인터뷰 담당)
> **모델**: Gemini 2.5 Flash (대용량 인터뷰 누적 처리), Claude Sonnet 4.5 (인사이트 추출)
> **예산**: 월 15,000원
> **빌드 기간 추정**: 3~4일

---

## 🎯 미션

대표님의 4월 진행 중인 고객 인터뷰 10건을 가이드·기록·분석한다. 8월 베타테스트 피드백 정리에도 재활용.

### 해결하는 문제

1차 사업계획서 탈락 원인 1번: **"고객 검증 부재"**.
이 봇이 만들어낼 자산:
- 인터뷰 가이드 (Argos 가설을 검증할 질문지)
- 인터뷰 기록 (구조화된 메모)
- 패턴 분석 (10건 누적 시 가설별 검증·반증 결과)
- 사업계획서 직접 인용 가능한 발언 추출

---

## 🎬 사용 시나리오

### 시나리오 1: 인터뷰 전 - 가이드 생성

```
대표: /interview prep
      대상: A보험 IT 보안팀장
      배경: 30인 규모, AWS 사용, 작년 KISA 점검 대비 컨설팅 수주 시도 중

봇:   📝 인터뷰 가이드 생성 중...

봇:   📋 Interview Prep — A보험 IT 보안팀장

      [Argos 가설 검증 우선순위]
      가설 1: "수탁사 점검 통과 실패 시 계약 해지 위험이 실제 존재"
      가설 2: "기존 DLP 솔루션은 너무 비싸거나 복잡"
      가설 3: "월 12만원이면 살 의향 있다"

      [질문지]

      🔥 워밍업
      1. 최근 1년간 가장 신경 썼던 보안 이슈는 무엇이었나요?
      2. 위탁자 측에서 받은 가장 까다로운 요구사항은?

      🎯 핵심 질문 (가설 1)
      3. 수탁사 보안 점검을 통과 못 한 적이 있나요? 결과는?
      4. 점검 항목 중 가장 부담스러운 것은?
      5. 현재 어떤 도구로 대비하시나요?

      🎯 핵심 질문 (가설 2)
      6. 도입 검토했던 보안 도구가 있나요? 도입 못 한 이유?
      7. 예산이 무제한이라면 어떤 도구가 필요한가요?

      💰 가격 검증 (가설 3)
      8. 만약 KISA 점검 항목을 자동 진단하는 SaaS가 월 12만원이라면?
      9. 의사결정자가 누구인가요? 결정 사이클은?

      🔮 미래
      10. 1년 뒤 이 영역이 어떻게 바뀔 거라 보시나요?

      [주의 사항]
      • Argos를 미리 설명하지 마세요. 문제 발견 → 솔루션 제시 순서.
      • "예/아니오"보다 "구체적 사례"를 끌어내세요.
      • 발언 그대로 받아 적기 (해석·재정리는 인터뷰 후).

      [녹음 동의 스크립트]
      "오늘 대화는 제품 개발 참고용으로 메모하려 합니다.
       녹음해도 괜찮을까요? 외부 공개는 절대 없습니다."
```

### 시나리오 2: 인터뷰 후 - 기록·정리

```
대표: /interview log
      대상: A보험 IT 보안팀장
      날짜: 2026-04-15
      [녹취록 또는 메모 첨부 또는 텍스트 입력]

봇:   📝 정리 중...

봇:   📋 Interview Log #007 — A보험

      [요약]
      30인 규모 보험사 IT 보안팀장. 작년 KISA 점검에서 3개 항목 미흡 받음.
      현재 외부 컨설팅 + 자체 체크리스트로 대응 중. 자동화 솔루션에 강한 관심.

      [가설 검증 결과]
      가설 1 (수탁사 점검 위험) ✅ 강하게 검증됨
        근거: "작년에 미흡 받은 후 위탁자 측에서 시정 조치 보고서 요구"
      가설 2 (기존 솔루션 부적합) ⚠️ 부분 검증
        근거: "DLP는 너무 무거움, 우리 규모엔 과함" 그러나 무료 도구로 충분하다는 의견
      가설 3 (월 12만원 가격) ❓ 미검증
        근거: 가격 직접 질문 누락. 다음 인터뷰에서 보강 필요.

      [핵심 발언 (사업계획서 인용 가능)]
      💬 "위탁자가 시정 조치 보고서를 요구하는데 매번 수작업으로 만드는 게 가장 큰 부담"
      💬 "보안 도구는 많은데 우리 규모(30인)에 맞는 게 없다"
      💬 "월 30만원 미만이면 결재 없이 결정 가능"

      [놓친 질문 (다음 인터뷰)]
      • 가격 민감도 (12만원 vs 20만원)
      • 도입 결정 사이클 (며칠?)

      [Argos 적용 인사이트]
      • "시정 조치 보고서 자동 생성" 기능 우선순위 ↑
      • 30인 규모를 1차 타겟 (이미 명시)
      • 가격 책정 재검토: 30만원 미만 사인 권한이 있다면 가격 상향 여지
```

### 시나리오 3: 누적 분석 - 패턴 추출

```
대표: /interview insight

봇:   📊 인터뷰 7건 누적 분석 중...
      (Gemini 2.5 Flash: 1M 토큰 컨텍스트로 전체 통합 분석)

봇:   📋 Interview Insights — 7건 종합

      [가설 검증 종합]
      | 가설 | 검증 | 반증 | 미검증 |
      |---|---|---|---|
      | 수탁사 점검 위험 | 6 | 0 | 1 |
      | 기존 솔루션 부적합 | 4 | 1 | 2 |
      | 월 12만원 가격 | 2 | 1 | 4 |

      [반복 등장 키워드]
      "시정 조치 보고서" (6/7 인터뷰) ← 가장 강한 페인 포인트
      "30인 규모에 맞는 도구 없음" (5/7)
      "위탁자 요구사항 변동" (5/7)

      [숨어있던 발견]
      ⚠️ 7건 중 4건이 "보안 담당자가 따로 없음" 언급
         → 1차 타겟 페르소나 재정의 필요? (보안팀장 → 일반 IT 담당자)

      ⚠️ 가격 검증 미흡 (2/7만 가격 질문 답변)
         → 다음 3건 인터뷰에서 가격 질문 필수

      [사업계획서 보강 자료]
      📎 인용 가능 발언 12개 (자세히: /interview quotes)
      📎 시장 검증 통계: 86% (6/7) "시정 조치 보고서가 가장 큰 부담"

      [다음 액션]
      1. 인터뷰 3건 더 (가격 질문 필수)
      2. 1차 타겟 페르소나 재검토 회의
      3. § 3 (시장 검증)에 위 통계 반영
```

---

## 🛠 빌드 스펙

### 디렉토리 구조

```
bots/interview_companion/
├── pyproject.toml
├── Dockerfile
├── railway.toml
├── README.md
├── prompts/
│   ├── prep_guide.md
│   ├── log_summary.md
│   └── pattern_analysis.md
├── data/
│   └── argos_hypotheses.yaml      # 검증할 가설 목록
└── src/interview_companion/
    ├── __init__.py
    ├── main.py
    ├── commands.py
    ├── interview_prep.py          # 가이드 생성
    ├── interview_logger.py        # 기록·정리
    ├── insight_extractor.py       # 누적 분석
    ├── storage.py                 # Postgres 저장
    └── ui.py
```

### 데이터 모델

```sql
-- migrations/001_interviews.sql
CREATE TABLE interviews (
    id SERIAL PRIMARY KEY,
    interview_number INT,
    target_name TEXT,
    target_role TEXT,
    target_company TEXT,
    target_company_size TEXT,
    interview_date DATE,
    raw_notes TEXT,
    summary JSONB,                 -- 봇이 생성한 구조화 요약
    hypotheses_results JSONB,      -- 가설별 검증/반증/미검증
    quotes JSONB,                  -- 인용 가능 발언 배열
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE hypotheses (
    id SERIAL PRIMARY KEY,
    hypothesis_id TEXT UNIQUE,
    statement TEXT,
    priority INT,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_interviews_date ON interviews(interview_date DESC);
```

### 핵심 인터페이스

#### `interview_prep.py`

```python
class InterviewPrep:
    def __init__(self, llm: LLMRouter, hypotheses_path: str):
        self.llm = llm
        self.hypotheses = self._load_hypotheses(hypotheses_path)

    async def generate_guide(
        self,
        target: InterviewTarget,
        focus_hypotheses: list[str] | None = None,
        user_id: str = "",
    ) -> InterviewGuide:
        """
        대상 정보 + 검증할 가설 → 인터뷰 가이드 생성.
        Sonnet 호출 1회.
        """
        ...
```

#### `interview_logger.py`

```python
class InterviewLogger:
    async def log(
        self,
        target: InterviewTarget,
        raw_content: str,            # 녹취 또는 메모
        user_id: str,
    ) -> InterviewLog:
        """
        1. Gemini Flash로 1차 요약 (긴 녹취 처리)
        2. Sonnet으로 가설 검증 결과 + 인용 추출
        3. Postgres 저장
        """
        ...
```

#### `insight_extractor.py`

```python
class InsightExtractor:
    async def analyze_all(self, user_id: str) -> InsightReport:
        """
        모든 인터뷰 + 가설 → Gemini 2.5 Flash로 통합 분석.
        1M 토큰 컨텍스트 활용.
        """
        # 1. DB에서 모든 인터뷰 로드
        interviews = await self.storage.list_all()

        # 2. 통합 컨텍스트 구성
        context = self._build_context(interviews, self.hypotheses)

        # 3. Gemini Flash 1회 호출 (대용량 컨텍스트)
        request = LLMRequest(
            task_type=TaskType.LARGE_CONTEXT,
            system=PATTERN_ANALYSIS_PROMPT,
            messages=[{"role": "user", "content": context}],
            user_id=user_id,
            bot_name="interview_companion",
            max_tokens=3000,
        )
        response = await self.llm.call(request)

        return self._parse_insights(response)

    async def find_quotes(
        self,
        keyword: str | None = None,
        hypothesis_id: str | None = None,
    ) -> list[Quote]:
        """사업계획서용 인용문 검색 (Postgres SQL, LLM 불필요)"""
        ...
```

### 슬래시 커맨드

```python
class InterviewCommands(app_commands.Group):
    name = "interview"

    @app_commands.command(description="인터뷰 가이드 생성")
    async def prep(
        self,
        interaction: discord.Interaction,
        target_name: str,
        target_role: str,
        target_company: str,
        company_size: str,
        background: str,
    ):
        ...

    @app_commands.command(description="인터뷰 기록·정리")
    async def log(
        self,
        interaction: discord.Interaction,
        target_name: str,
        date: str,
        notes: discord.Attachment | None = None,
        text: str | None = None,
    ):
        ...

    @app_commands.command(description="누적 인터뷰 패턴 분석")
    async def insight(self, interaction: discord.Interaction):
        ...

    @app_commands.command(description="인용 가능 발언 검색")
    async def quotes(
        self,
        interaction: discord.Interaction,
        keyword: str | None = None,
        hypothesis: str | None = None,
    ):
        ...
```

### `data/argos_hypotheses.yaml`

```yaml
hypotheses:
  - id: H1_subcontractor_risk
    statement: 수탁사 보안 점검 통과 실패 시 계약 해지·위탁자 신뢰 손상 위험이 실제 존재한다
    priority: 1
    related_features: [점검_자동진단, 시정조치_리포트]

  - id: H2_existing_solutions_unfit
    statement: 30인 규모 위탁사가 사용할 만한 보안 도구가 시장에 부족하다
    priority: 2
    related_features: [경량_PC앱, SaaS_대시보드]

  - id: H3_pricing_120k
    statement: 월 12만원 이하 가격이면 30인 규모 위탁사가 도입 의사 있다
    priority: 1
    related_features: [구독_과금]

  - id: H4_compliance_report_burden
    statement: 위탁자 요구 시정 조치 보고서 작성이 가장 큰 운영 부담이다
    priority: 1
    related_features: [리포트_자동생성]
```

> 가설 목록은 `Argos_Context.md`에서 추출. 인터뷰 진행 중 가설 추가·수정 가능.

---

## 💰 비용 예산 산정

| 시나리오 | 모델 | 입력 | 출력 | 추정 비용 |
|---|---|---|---|---|
| 가이드 생성 | Sonnet | 3,000 (캐시 2,000) + 500 | 2,000 | 약 600원 |
| 로그 (짧은 메모) | Gemini Flash + Sonnet | 5,000 + 3,000 | 1,500 + 1,500 | 약 400원 |
| 로그 (긴 녹취) | Gemini Flash + Sonnet | 30,000 + 3,000 | 1,500 + 1,500 | 약 700원 |
| 누적 분석 (10건) | Gemini Flash | 50,000 | 3,000 | 약 800원 |

### 월 사용 시뮬레이션 (5월 기준 — 인터뷰 활발)

- 가이드 10회 × 600원 = 6,000원
- 로그 10회 × 평균 600원 = 6,000원
- 누적 분석 5회 × 800원 = 4,000원
- → 약 16,000원

> 한도 15,000원 거의 도달. 인터뷰 시즌 끝나면 사용량 급감 예상.

---

## ⚠️ 주의사항

### 1. 인터뷰 데이터 민감성
인터뷰이의 발언·소속이 DB에 저장됨. **개인정보보호법 적용 가능**.
- 익명화: `target_name`은 이니셜·역할로만 저장 권장
- 동의: 봇 사용 전 인터뷰이 동의 필수
- 보관: 6개월 후 자동 익명화 또는 삭제 cron job

### 2. 녹취록 외부 LLM 전송
긴 녹취가 Gemini API로 전송됨. Argos 정신과 모순될 수 있음. 명시 안내:
- "이 봇은 녹취를 Google Gemini API로 전송합니다."
- 옵션: 민감 인터뷰는 봇 안 쓰고 직접 정리

### 3. 봇 종합 결과의 위험
"가설 6/7 검증" 같은 숫자가 절대적으로 보일 위험. 출력 끝에 항상:
"이 분석은 자동 추출 결과입니다. 실제 사업계획서 작성 전 발언을 직접 확인하세요."

### 4. 다국어
인터뷰가 한국어 위주지만 일부 영어 섞일 가능. Sonnet은 한영 혼용 처리 우수, Gemini Flash도 OK.

---

## ✅ 완료 체크리스트

- [ ] `argos_hypotheses.yaml` 가설 4~6개 정의
- [ ] Postgres 마이그레이션 적용
- [ ] 슬래시 커맨드 4종 동작 (`prep`, `log`, `insight`, `quotes`)
- [ ] 가이드 생성: 가설 검증 질문 우선 포함 확인
- [ ] 로그: 인용 가능 발언 추출 정확
- [ ] 누적 분석: 10건 입력 시 통합 컨텍스트 처리 정상
- [ ] 응답 시간: 가이드 < 30초, 로그 < 60초, 누적 < 90초
- [ ] 인터뷰이 익명화 옵션 동작
- [ ] 6개월 자동 익명화 cron 설정
- [ ] README에 "외부 LLM 전송" 안내

---

다음 문서: `05_DESIGN_ECHO.md`
