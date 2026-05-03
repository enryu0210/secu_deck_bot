# 05. Design Echo — 디자인 시스템·핸드오프 봇

> **Phase**: 2
> **주 사용자**: 디자인팀 2명
> **모델**: Gemini 2.5 Flash (이미지 이해), Claude Sonnet 4.5 (UX 라이팅 검토)
> **예산**: 월 25,000원
> **빌드 기간 추정**: 3~4일

---

## 🎯 미션

Argos PC 앱·관리자 대시보드·랜딩페이지(7월 오픈)를 일관된 디자인 시스템으로 만든다. 디자인-개발 핸드오프를 자동화한다.

### 해결하는 문제

1. 화면 수가 늘면서 토큰·컴포넌트 일관성 깨짐
2. 디자인-개발 핸드오프 시 spec 작성 부담
3. 보안 컴플라이언스 SaaS 톤(신뢰감·명확함) 유지

---

## 🎬 사용 시나리오

### 시나리오 1: 디자인 일관성 체크

```
디자이너: /design check
        [PC 앱 새 화면 시안 PNG 첨부]

봇:    🎨 디자인 분석 중...
       (Gemini 2.5 Flash로 이미지 분석)

봇:    📋 Design Check #024

       [감지된 토큰]
       Color
       • Primary: #2563EB (✅ DS 일치)
       • Background: #F8FAFC (⚠️ #F9FAFB가 표준)
       • Border: #D1D5DB (✅)

       Typography
       • Header: Pretendard 24px / 600 (✅)
       • Body: Pretendard 14px / 400 (⚠️ DS 표준 15px)

       Spacing
       • 카드 padding: 18px (⚠️ DS 16/20/24 그리드 벗어남)

       [컴포넌트]
       • Button (Primary) ✅
       • Card ✅
       • Toast (신규) ⚠️ 디자인 시스템 미등록 — 추가 필요?

       [Argos 톤 체크]
       문구 "에러가 발생했어요!" → 톤 부적합
       Argos 톤은 신뢰감·명확함. 권장:
       • "스캔이 중단되었습니다. 다시 시도하시겠습니까?"

       [Action]
       1. Background #F9FAFB로 통일
       2. Body 폰트 15px 조정
       3. Card padding 16/20 중 선택
       4. Toast 컴포넌트 DS 등록 결정
       5. 에러 메시지 톤 조정
```

### 시나리오 2: 개발 핸드오프 spec 생성

```
디자이너: /design spec
         [관리자 대시보드 화면 첨부]

봇:    📐 Spec 생성 중...

봇:    📋 Dev Handoff Spec — 관리자 대시보드 / 점검 결과 페이지

       [레이아웃]
       • 컨테이너: max-width 1280px, padding 32px 40px
       • 그리드: 3 컬럼, gap 24px
       • 헤더 높이: 64px (sticky)

       [컴포넌트]

       1. ScanResultCard
          background: #FFFFFF
          border: 1px solid #E5E7EB
          border-radius: 8px
          padding: 24px
          내부 레이아웃:
          - 타이틀: 16px / 600 / #111827
          - 메타: 12px / 400 / #6B7280
          - 점수 배지: 위 우측, 32px diameter

       2. SeverityBadge
          variants:
          - HIGH: bg #FEE2E2, text #991B1B
          - MED:  bg #FEF3C7, text #92400E
          - LOW:  bg #DBEAFE, text #1E40AF

       [인터랙션]
       • 카드 hover: shadow elevation 2
       • 클릭: 상세 모달 (별도 spec)

       [반응형]
       • < 1024px: 2 컬럼
       • < 640px: 1 컬럼

       [접근성]
       • SeverityBadge에 aria-label 필수
       • 색만으로 의미 전달 금지 → 아이콘 추가 권장

       [개발 참고]
       이 화면은 React + Tailwind 가정. 토큰은 tailwind.config.js 정의 사용.
```

### 시나리오 3: UX 라이팅 검토

```
디자이너: /design copy
         화면: 회원가입 완료 후
         현재 문구: "축하합니다! Argos에 오신 걸 환영합니다 🎉"
         목적: 사용자가 다음 단계로 자연스럽게 이동

봇:    ✏️ UX 라이팅 검토 중...

봇:    📋 Copy Review

       [현재 문구 분석]
       • 톤: 캐주얼·축제 (Argos 톤 ⚠️)
       • B2B 보안 SaaS의 사용자(IT 담당자)에게 다소 가벼움
       • 다음 액션 안내 부재

       [Argos 톤 가이드 적용]
       원칙: 신뢰감 / 명확함 / 효율
       금기: 과도한 이모지, 가벼운 감탄사

       [추천 안 3가지]

       옵션 A — 차분·실용
       "Argos 가입이 완료되었습니다.
        첫 보안 점검을 시작하려면 [에이전트 다운로드]를 클릭하세요."

       옵션 B — 신뢰·전문
       "환영합니다.
        시작 가이드를 따라 5분 안에 첫 진단을 마칠 수 있습니다."

       옵션 C — 행동 우선
       "계정이 준비되었습니다.
        다음: 1) PC 앱 설치 → 2) 첫 점검 실행"

       [추천] B
       이유: B2B 신뢰감 + "5분"이라는 구체적 기대치 제공.
       의사결정자(IT팀장)가 보더라도 진중함 유지.
```

---

## 🛠 빌드 스펙

### 디렉토리 구조

```
bots/design_echo/
├── pyproject.toml
├── Dockerfile
├── railway.toml
├── README.md
├── prompts/
│   ├── system_base.md
│   ├── consistency_check.md
│   ├── handoff_spec.md
│   └── copy_review.md
├── design_system/
│   ├── tokens.yaml              # Argos DS 토큰 정의
│   ├── components.yaml          # 등록된 컴포넌트
│   └── tone_guide.yaml          # UX 라이팅 톤
└── src/design_echo/
    ├── __init__.py
    ├── main.py
    ├── commands.py
    ├── consistency_checker.py
    ├── spec_generator.py
    ├── copy_reviewer.py
    └── ui.py
```

### `design_system/tokens.yaml` — Argos 디자인 시스템

```yaml
# 디자인팀과 함께 작성 (이 파일이 봇의 "정답지")
colors:
  primary:
    50: "#EFF6FF"
    500: "#2563EB"
    600: "#1D4ED8"
    900: "#1E3A8A"
  semantic:
    danger: "#DC2626"
    warning: "#D97706"
    success: "#059669"
    info: "#2563EB"
  neutral:
    bg_primary: "#FFFFFF"
    bg_secondary: "#F9FAFB"
    border: "#E5E7EB"
    text_primary: "#111827"
    text_secondary: "#6B7280"

typography:
  fonts:
    sans: Pretendard
    mono: JetBrains Mono
  sizes:
    h1: { size: 32px, weight: 700, line_height: 1.3 }
    h2: { size: 24px, weight: 600, line_height: 1.4 }
    body: { size: 15px, weight: 400, line_height: 1.6 }
    caption: { size: 13px, weight: 400, line_height: 1.5 }

spacing:
  scale: [4, 8, 12, 16, 20, 24, 32, 40, 48, 64]
  unit: px

radius:
  sm: 4px
  md: 8px
  lg: 12px
  full: 9999px

elevation:
  card: "0 1px 3px rgba(0,0,0,0.06)"
  popover: "0 4px 12px rgba(0,0,0,0.1)"
```

### `design_system/tone_guide.yaml` — Argos UX 라이팅 톤

```yaml
identity:
  product: Argos
  category: AI 보안 컴플라이언스 SaaS
  audience: 30인 규모 IT 담당자, 위탁사 보안팀장

principles:
  - 신뢰감: 과장·과약 금지, 사실 기반
  - 명확함: 모호한 표현 회피, 다음 액션 명시
  - 효율: 짧게, 본질만, 사용자 시간 존중

forbidden:
  - 과도한 이모지 (제로 정책: 메시지당 0~1개만)
  - 캐주얼 감탄사 ("우와!", "헉")
  - 사용자 책망 ("잘못 입력하셨습니다")
  - 모호한 보안 용어 단독 사용 (해설 없이 "DLP", "RBAC" 등)

examples:
  good:
    - "스캔이 완료되었습니다. 위험 항목 3건을 확인하세요."
    - "현재 정책을 적용하면 12개 파일이 격리됩니다. 진행하시겠습니까?"
  bad:
    - "축하합니다! 보안이 강화되었어요 🎉🎉"
    - "오류가 발생했어요. 죄송합니다."
    - "RBAC 설정이 완료되었습니다." (해설 없이)

error_messages:
  pattern: "[무엇이 일어났나] + [사용자가 할 수 있는 것]"
  example:
    bad: "오류가 발생했어요!"
    good: "네트워크 연결이 끊어졌습니다. 다시 시도하거나 관리자에게 문의하세요."
```

### 핵심 인터페이스

#### `consistency_checker.py`

```python
class ConsistencyChecker:
    def __init__(self, llm: LLMRouter, ds_dir: str):
        self.llm = llm
        self.tokens = self._load_yaml(f"{ds_dir}/tokens.yaml")
        self.components = self._load_yaml(f"{ds_dir}/components.yaml")
        self.tone = self._load_yaml(f"{ds_dir}/tone_guide.yaml")

    async def check(self, image_bytes: bytes, user_id: str) -> CheckResult:
        """Gemini Vision으로 시안 분석 → DS 토큰 매칭"""
        request = LLMRequest(
            task_type=TaskType.VISION_DESIGN,
            system=self._build_system_prompt(),
            messages=[{"role": "user", "content": "이 디자인 시안의 색상·폰트·간격·컴포넌트를 추출해주세요. JSON으로 응답하세요."}],
            images=[image_bytes],
            user_id=user_id,
            bot_name="design_echo",
            max_tokens=2000,
        )
        response = await self.llm.call(request)
        extracted = json.loads(response.text)

        # 추출된 토큰 vs DS 토큰 비교 (룰베이스, LLM 호출 X)
        diffs = self._compare(extracted, self.tokens)

        # 추가: 톤 체크 (텍스트 추출되면 LLM에 한 번 더)
        text_in_image = extracted.get("texts", [])
        tone_issues = await self._check_tone(text_in_image, user_id)

        return CheckResult(extracted=extracted, diffs=diffs, tone_issues=tone_issues)
```

#### `spec_generator.py`

```python
class SpecGenerator:
    async def generate(
        self,
        image_bytes: bytes,
        screen_name: str,
        user_id: str,
    ) -> HandoffSpec:
        """
        Gemini Vision으로 분석 → 개발자가 바로 쓸 spec 생성.
        Tailwind 클래스 추천 포함.
        """
        ...
```

#### `copy_reviewer.py`

```python
class CopyReviewer:
    async def review(
        self,
        screen_context: str,
        purpose: str,
        current_copy: str,
        user_id: str,
    ) -> CopyReview:
        """
        Sonnet으로 Argos 톤 가이드 적용 → 3가지 안 + 추천.
        """
        ...
```

### 슬래시 커맨드

```python
class DesignCommands(app_commands.Group):
    name = "design"

    @app_commands.command(description="디자인 시스템 일관성 체크")
    async def check(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
    ):
        ...

    @app_commands.command(description="개발 핸드오프 spec 생성")
    async def spec(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        screen_name: str,
    ):
        ...

    @app_commands.command(description="UX 라이팅 검토")
    async def copy(
        self,
        interaction: discord.Interaction,
        screen_context: str,
        purpose: str,
        current_copy: str,
    ):
        ...
```

---

## 💰 비용 예산 산정

| 시나리오 | 모델 | 입력 | 출력 | 추정 비용 |
|---|---|---|---|---|
| 일관성 체크 (이미지 1장) | Gemini Flash | 5,000 (이미지) + 1,000 | 1,500 | 약 50원 |
| 톤 체크 추가 (텍스트만) | Sonnet | 2,000 | 800 | 약 200원 |
| 핸드오프 spec | Gemini Flash | 5,000 + 500 | 2,500 | 약 60원 |
| 카피 리뷰 | Sonnet | 2,500 | 1,500 | 약 350원 |

### 월 사용 시뮬레이션

- 디자이너 2명 × 주 5회 × 4주 = 40회/월
- 평균 200원 × 40회 = 8,000원
- 카피 리뷰 추가 20회 × 350원 = 7,000원
- → 약 15,000원

> 한도 25,000원 충분. 향후 카피 리뷰 늘면 한도 도달.

---

## ⚠️ 주의사항

### 1. 이미지 형식
- PNG, JPG 지원. PSD·Figma 파일은 직접 분석 불가 → "PNG로 export 후 업로드" 안내.
- Figma 플러그인으로 봇 호출하는 통합은 추후 검토 (현재 범위 외).

### 2. 디자인 시스템이 살아있는 문서
`tokens.yaml`, `components.yaml`이 디자인팀의 실제 작업과 동기화 필수.
- 디자인팀이 직접 수정 가능한 위치 (GitHub 또는 Notion 미러)
- 변경 시 봇 자동 재로드 (mtime 감지)
- 분기별 점검

### 3. Gemini의 한국어 톤 한계
Gemini가 한국어 UX 라이팅 분석에서 가끔 부자연스러움. 톤 체크 부분은 **무조건 Sonnet** 사용 (router에서 강제).

### 4. 디자인 자산 외부 전송
시안 이미지가 Google API로 전송됨. 미공개 경쟁 정보 포함 시 주의 안내.

---

## ✅ 완료 체크리스트

- [ ] `tokens.yaml`, `components.yaml`, `tone_guide.yaml` 디자인팀과 함께 작성
- [ ] 슬래시 커맨드 3종 (`check`, `spec`, `copy`) 동작
- [ ] PNG·JPG 첨부 처리 정상
- [ ] 색상 추출 정확도: 알려진 시안 5개 테스트 시 80% 이상
- [ ] 톤 체크: Argos 톤 가이드 위반 사례 정확히 지적
- [ ] 핸드오프 spec: 개발자 5명 중 3명 이상 "쓸 만하다" 평가
- [ ] 응답 시간: < 60초
- [ ] DS 파일 변경 시 자동 재로드 동작
- [ ] README에 사용법 + 한계 안내

---

다음 문서: `06_CHIEF_OF_STAFF.md`
