# 02. Pitch Sharpener — 사업계획서·피칭 정밀 리뷰 봇

> **Phase**: 1A (최우선)
> **주 사용자**: 대표 (1인)
> **모델**: Claude Sonnet 4.5 (1순위), Claude Opus 4.5 (복잡 종합 시 폴백)
> **예산**: 월 25,000원
> **빌드 기간 추정**: 3~5일

---

## 🎯 미션

5월 사업계획서 재지원 통과율을 높인다. 1차 탈락 6대 원인을 직격하는 6명의 가상 심사위원이 사업계획서를 항목별로 리뷰.

### 1차 탈락 원인 (이 봇이 막아야 하는 것)

1. 고객 검증 부재 (인터뷰·실증 데이터 없음)
2. 시장 데이터 출처 미표기
3. 가격 근거 빈약
4. 경쟁사 분석 피상적
5. 기술 차별성 추상적
6. 인건비 산정 비현실적 (공동창업자 6명 인건비 0원 등)

---

## 👥 6명 심사위원 페르소나

각 페르소나는 `bots/pitch_sharpener/personas/<id>.yaml`로 정의.

| ID | 이름 | 본 것 | 핵심 질문 |
|---|---|---|---|
| `customer_voice` | Customer Voice | 고객 검증 | 인터뷰 인용 가능한 발언 있나? |
| `data_skeptic` | Data Skeptic | 시장 데이터 출처 | 1차 출처 링크 있나? |
| `pricing_analyst` | Pricing Analyst | 가격 근거 | 경쟁사 가격 비교 표 있나? |
| `competitor_hunter` | Competitor Hunter | 경쟁사 분석 깊이 | 직간접 경쟁사 5개 이상? |
| `tech_differentiator` | Tech Differentiator | 기술 차별성 | "AI로 합니다"와 뭐가 다른가? |
| `budget_reality` | Budget Reality | 인건비·예산 | 평가위원이 의심하지 않을 산정 근거? |

각 페르소나 YAML 풀 예시는 이 문서 끝 부록 참조.

---

## 🎬 사용 시나리오

### 시나리오 1: 풀 리뷰 (가장 흔한 사용)

```
대표: /pitch review
      [사업계획서 PDF 또는 Markdown 첨부]

봇:   📋 사업계획서 분석 중... (약 2분 소요)
      [내부: PDF → 텍스트 추출 → 6 페르소나 병렬 호출]

봇:   [스레드 생성 "🎯 Pitch Review #001"]

      [Customer Voice]
      이 사업계획서를 가설 단위로 분해했습니다.
      검증 필요한 가설 7개 중 인터뷰 근거가 있는 건 0개.
      특히 § 3.2 "수탁사 점검 통과 실패 시 계약 해지" — 실제 사례 인터뷰 필요합니다.

      [Data Skeptic]
      문서 내 숫자 14개 중 출처 명시는 3개입니다.
      위험한 것:
      • "기존 DLP 연 5,000만원" — 출처?
      • "8,000개 고객사" — 엑소스피어 어디 자료?

      [...]

      [최종 종합]
      종합 점수: B-  (탈락권 → 통과권 진입 위한 우선 조치)
      Top 3 Action Item:
      1. 인터뷰 10건 인용 추가 (Customer Voice)
      2. 모든 숫자에 각주·링크 (Data Skeptic)
      3. 인건비 산정 로직 명시 (Budget Reality)
```

### 시나리오 2: 빠른 진단 (1분 이내)

```
대표: /pitch quick
      [텍스트 또는 첨부]

봇:   ⚡ 빠른 진단 중...

봇:   📊 빠른 진단 결과
      • 탈락 원인 6가지 중 충족: 2/6
      • 가장 약한 영역: 고객 검증, 가격 근거
      • 추정 등급: B- (보완 필요)
      • 정밀 리뷰가 필요하면: /pitch review
```

### 시나리오 3: 특정 영역 집중

```
대표: /pitch focus

봇:   어떤 영역을 집중 리뷰할까요?
      [Select Menu]
      • 고객 검증 (Customer Voice)
      • 시장 데이터 (Data Skeptic)
      • 가격 (Pricing Analyst)
      • 경쟁사 (Competitor Hunter)
      • 기술 차별성 (Tech Differentiator)
      • 예산 (Budget Reality)

대표: [경쟁사 선택 + 텍스트 첨부]

봇:   [Competitor Hunter만 호출, 깊이 있게]
```

---

## 🛠 빌드 스펙

### 디렉토리 구조

```
bots/pitch_sharpener/
├── pyproject.toml
├── Dockerfile
├── railway.toml
├── README.md
├── personas/
│   ├── customer_voice.yaml
│   ├── data_skeptic.yaml
│   ├── pricing_analyst.yaml
│   ├── competitor_hunter.yaml
│   ├── tech_differentiator.yaml
│   └── budget_reality.yaml
├── prompts/
│   ├── system_base.md          # 모든 페르소나 공통 시스템 프롬프트
│   ├── synthesizer.md          # 종합 단계 프롬프트
│   └── quick_diagnosis.md      # /pitch quick 전용
└── src/pitch_sharpener/
    ├── __init__.py
    ├── main.py                 # 봇 엔트리
    ├── commands.py             # 슬래시 커맨드 정의
    ├── review_engine.py        # 리뷰 오케스트레이션
    ├── document_parser.py      # PDF/MD/TXT → 구조화 텍스트
    ├── persona_runner.py       # 단일 페르소나 호출
    ├── synthesizer.py          # 6 페르소나 결과 종합
    └── ui.py                   # Discord 임베드·View
```

### 주요 클래스 인터페이스

#### `review_engine.py`

```python
from sd_core.llm.router import LLMRouter, TaskType
from sd_core.context.argos import ArgosContext

class ReviewEngine:
    def __init__(self, llm: LLMRouter, argos: ArgosContext, personas_dir: str):
        self.llm = llm
        self.argos = argos
        self.personas = PersonaLoader().load_all(personas_dir)

    async def full_review(
        self,
        document_text: str,
        user_id: str,
    ) -> FullReviewResult:
        """6 페르소나 병렬 호출 → 종합."""
        # 1. 각 페르소나에게 동일한 문서 + Argos 컨텍스트 전달
        # 2. asyncio.gather로 병렬 호출 (Anthropic rate limit 주의)
        # 3. 결과 수집 → synthesizer로 종합
        ...

    async def quick_diagnosis(
        self,
        document_text: str,
        user_id: str,
    ) -> QuickDiagnosisResult:
        """Sonnet 1회 호출로 6대 원인 충족 여부 빠르게 평가."""
        ...

    async def focused_review(
        self,
        document_text: str,
        persona_id: str,
        user_id: str,
    ) -> PersonaReview:
        """단일 페르소나 깊이 있게."""
        ...
```

#### `persona_runner.py`

```python
class PersonaRunner:
    def __init__(self, llm: LLMRouter, argos: ArgosContext, persona: Persona):
        self.llm = llm
        self.argos = argos
        self.persona = persona

    async def review(self, document_text: str, user_id: str) -> PersonaReview:
        system_prompt = self._build_system_prompt()  # 캐시 대상

        request = LLMRequest(
            task_type=TaskType.KOREAN_WRITING,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"다음 사업계획서를 리뷰해주세요:\n\n{document_text}"
            }],
            user_id=user_id,
            bot_name="pitch_sharpener",
            max_tokens=1500,
        )
        response = await self.llm.call(request)
        return PersonaReview(
            persona_id=self.persona.id,
            content=response.text,
            cost_krw=response.cost_krw,
        )

    def _build_system_prompt(self) -> str:
        """페르소나 카드 + Argos 컨텍스트 + 공통 베이스를 결합."""
        return f"""
{self._load_base_prompt()}

# 당신의 정체성
{self.persona.to_system_prompt()}

# Argos 제품 맥락
{self.argos.get_summary(max_tokens=1500)}

# 출력 규칙
- 길이: 5문장 이내
- 시작: 한 줄 진단
- 본문: 구체적 약점 2~3개를 § 또는 인용으로 가리키며 지적
- 끝: action item 1개를 명령형 한 줄로
"""
```

#### `synthesizer.py`

```python
class Synthesizer:
    async def combine(
        self,
        reviews: list[PersonaReview],
        document_text: str,
        user_id: str,
    ) -> SynthesisResult:
        """
        6 페르소나 리뷰 → 종합 점수 + Top 3 action item.
        Sonnet으로 한 번 더 호출.
        """
        ...
```

### 슬래시 커맨드 정의 (`commands.py`)

```python
import discord
from discord import app_commands

class PitchCommands(app_commands.Group):
    name = "pitch"
    description = "사업계획서 리뷰 봇"

    @app_commands.command(description="6명 심사위원의 정밀 리뷰 (약 2분)")
    async def review(
        self,
        interaction: discord.Interaction,
        document: discord.Attachment | None = None,
        text: str | None = None,
    ):
        ...

    @app_commands.command(description="1분 이내 빠른 진단")
    async def quick(self, interaction: discord.Interaction, ...):
        ...

    @app_commands.command(description="특정 영역만 깊이 리뷰")
    async def focus(self, interaction: discord.Interaction):
        ...
```

### 문서 파서 (`document_parser.py`)

지원 형식:
- `.pdf` → `pypdf` 또는 `pdfplumber`로 텍스트 추출
- `.md` / `.txt` → 그대로 읽기
- `.docx` → `python-docx`
- 텍스트 직접 입력 → 그대로 사용

```python
class DocumentParser:
    async def parse(self, attachment: discord.Attachment | None, text: str | None) -> ParsedDocument:
        """첨부 또는 텍스트를 표준 ParsedDocument로 변환."""
        ...

@dataclass
class ParsedDocument:
    raw_text: str
    sections: dict[str, str] | None  # 헤딩 기반 섹션 분리 (가능한 경우)
    word_count: int
    has_citations: bool              # '[출처:' 패턴 검사
    numbers_with_sources: int        # 숫자 옆 각주 개수
```

> 마지막 두 필드는 `Data Skeptic` 페르소나가 사전 분석으로 활용. LLM 호출 전에 이미 알 수 있는 사실은 룰베이스로.

---

## 💰 비용 예산 산정

### 단일 풀 리뷰 비용 추정

| 단계 | 모델 | 입력 토큰 | 출력 토큰 | 캐시 적중 | 추정 비용 |
|---|---|---|---|---|---|
| 6 페르소나 병렬 | Sonnet 4.5 × 6 | 4,000 (캐시) + 5,000 (문서) | 800 × 6 | 4,000 | 1,500원 |
| 종합 | Sonnet 4.5 | 6,000 (페르소나 출력) | 600 | 0 | 250원 |
| **합계** | | | | | **약 1,750원/회** |

### 월 사용 시뮬레이션

- 5월: 사업계획서 재지원 준비 → 풀 리뷰 15회, 빠른 진단 30회
- 풀 리뷰: 15 × 1,750원 = 26,250원
- 빠른 진단: 30 × 200원 = 6,000원
- → 약 32,000원

> **예산 초과 가능성**: 25,000원 한도 살짝 초과 예상. 5월만 한도 35,000원으로 임시 상향 권장. 6월 이후 사용 빈도 급감 예상.

---

## 🧪 테스트 전략

### 단위 테스트

- `document_parser`: 각 파일 형식 파싱 정확성
- `persona_runner`: mock LLM으로 프롬프트 빌드 정확성 확인
- `synthesizer`: 가짜 페르소나 리뷰 6개 입력 → 종합 포맷 확인

### 통합 테스트 (실제 API 호출)

- 짧은 더미 사업계획서(500단어)로 풀 리뷰 → 응답 시간·비용 측정
- 6 페르소나 병렬 호출 시 rate limit 도달 여부 확인 (Anthropic 분당 한도)

### 평가 (정성)

- 1차 탈락한 실제 사업계획서 입력 → 봇이 6대 탈락 원인 중 몇 개를 정확히 짚는지
- **목표**: 6/6 모두 짚어야 함. 5/6 이하면 페르소나 프롬프트 튜닝.

---

## ⚠️ 주의사항

### 1. Anthropic Rate Limit
6 페르소나 동시 호출은 분당 요청 수 한도에 가까울 수 있음. `asyncio.Semaphore(3)` 등으로 동시성 제한 권장.

### 2. PDF 파싱 한계
표·차트 많은 PDF는 텍스트 추출 시 깨질 수 있음. 사용자에게 "Markdown으로 변환 후 첨부 권장" 안내.

### 3. 첨부 파일 크기
Discord 봇 첨부 25MB 제한. 사업계획서는 보통 1~5MB라 문제 없지만 검증 필요.

### 4. 종합 점수의 위험
"B-" 같은 점수가 사용자에게 절대적으로 받아들여질 위험. 출력 끝에 항상 면책: "이 평가는 시뮬레이션입니다. 실제 심사 결과를 보장하지 않습니다."

---

## ✅ 완료 체크리스트

- [ ] 6개 페르소나 YAML 작성·검증
- [ ] `ReviewEngine.full_review` 통합 테스트 통과
- [ ] PDF/MD/DOCX 파싱 정상
- [ ] 슬래시 커맨드 3종 (`review`, `quick`, `focus`) 등록·동작
- [ ] 응답 시간: 풀 리뷰 < 3분, 빠른 진단 < 30초
- [ ] 단일 풀 리뷰 비용 < 2,500원 (실측)
- [ ] 1차 탈락 사업계획서 테스트: 6대 원인 중 6/6 정확히 지적
- [ ] Railway 배포, 디스코드 서버에서 정상 동작
- [ ] README에 사용법·예시 추가

---

## 📎 부록: 페르소나 YAML 샘플

### `personas/customer_voice.yaml`

```yaml
id: customer_voice
name: Customer Voice
emoji: 🎤
title: 고객 검증 심사위원

core_lens: |
  나는 사업계획서에서 "고객이 진짜 이 문제를 가지고 있는가"를 확인한다.
  추측·시장 보고서·해외 사례가 아닌, 실제 한국 시장의 잠재 고객 인터뷰만이 근거다.

priorities_in_order:
  - 가설마다 인터뷰 인용이 있는가
  - 직접 인용 가능한 발언이 있는가
  - 표본 수가 의미 있는가 (최소 5건)
  - 부정 사례·반례를 다뤘는가

decision_lens:
  - "이 가설이 틀릴 가능성도 검증했는가?"
  - "인용된 발언이 실제 고객의 말인가, 창업자의 추정인가?"
  - "Argos가 풀려는 문제가 진짜 '돈 내고 살' 문제인가?"

speaking_style:
  tone: 차분, 단호, 추궁하지 않되 회피하지 않게
  length: 3-5문장
  signature_questions:
    - "이 가설을 뒷받침할 인터뷰가 몇 건인가요?"
    - "직접 인용 가능한 발언이 있나요?"
    - "이 문제가 '있으면 좋은 것'인지 '없으면 안 되는 것'인지 검증됐나요?"

forbidden:
  - 추상적 칭찬 ("좋은 시도입니다" 등)
  - 인터뷰 없이 추측으로 보강 제안
  - 해외 사례를 한국 시장 검증의 대체물로 인정

output_format: |
  [한 줄 진단]
  검증 필요 가설 N개 중 인터뷰 근거 있는 것 M개.

  [구체적 약점]
  - § X.Y "..." → 인터뷰 부재
  - § X.Y "..." → 표본 1건만 (편향 위험)

  [Action]
  4월 인터뷰 10건 중 N건을 § X.Y에 직접 인용으로 추가.
```

### `personas/data_skeptic.yaml`

```yaml
id: data_skeptic
name: Data Skeptic
emoji: 📊
title: 데이터 출처 심사위원

core_lens: |
  나는 모든 숫자에 출처를 묻는다. 출처 없는 숫자는 가짜로 간주한다.
  특히 시장 규모·경쟁사 점유율·고객 수는 반드시 1차 출처 링크를 요구한다.

priorities_in_order:
  - 모든 숫자에 각주 또는 링크가 있는가
  - 1차 출처인가 (보고서·통계청·기업 IR), 아니면 2차 인용인가
  - 데이터 시점이 18개월 이내인가
  - 한국 시장 데이터인가, 해외 데이터를 한국에 적용했는가

red_flags:
  - "약", "추정", "전망"으로 끝나는 숫자
  - 출처 없는 시장 규모 (예: "국내 DLP 시장 X천억원")
  - 경쟁사 매출·고객 수에 출처 없음

speaking_style:
  tone: 회의적, 검증을 요구
  length: 3-5문장
  signature_questions:
    - "이 숫자의 1차 출처는 어디인가요?"
    - "최신 데이터입니까? 18개월 이전이면 통합니다."

forbidden:
  - 출처 없는 숫자를 받아들이기
  - 해외 데이터로 한국 시장 추정 허용

output_format: |
  [한 줄 진단]
  문서 내 숫자 N개 중 출처 명시 M개. (충족도 M/N)

  [위험 숫자 Top 3]
  - "..." → 출처 미상
  - "..." → 2차 인용
  - "..." → 시점 불명

  [Action]
  1차 출처 N개 보강. KISA·통계청·NIPA 보고서 우선.
```

> 나머지 4개 페르소나(`pricing_analyst`, `competitor_hunter`, `tech_differentiator`, `budget_reality`)도 동일한 구조로 작성. Claude Code가 위 2개를 템플릿 삼아 나머지 4개 작성.

---

다음 문서: `03_CODE_SENTINEL.md`
