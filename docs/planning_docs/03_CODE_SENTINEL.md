# 03. Code Sentinel — 코드 리뷰·KISA 정합성 체크 봇

> **Phase**: 1B
> **주 사용자**: 개발팀 3명
> **모델**: Claude Haiku 4.5 (1순위), Claude Sonnet 4.5 (복잡 보안 리뷰 시 자동 승급)
> **예산**: 월 60,000원
> **빌드 기간 추정**: 3~5일

---

## 🎯 미션

Argos 개발팀의 매일 코드 작업을 보조한다. 일반 코드 리뷰가 아니라 **Argos 컨텍스트를 항상 들고 있는** 리뷰어 — 개인정보보호법·KISA 가이드라인·DoD 5220.22-M 준수를 자동 체크.

### Argos 코드베이스의 알려진 위험 (이 봇이 잡아야 하는 것)

`Argos_Context.md` § 10에 명시된 보안 이슈:
1. API 키·비밀번호 하드코딩
2. PII가 마스킹 없이 외부 LLM API로 전송
3. DoD 5220.22-M 표준 미준수 (랜덤 시드, 덮어쓰기 횟수 등)
4. `scanner_rules` 정규식의 false positive (sample, mock 누락)
5. 핵심 탐지 로직에 단위 테스트 부재
6. `security_policy.json` 스키마 정합성 깨짐
7. 레거시 코드(`src/legacy/`) 잔존

---

## 🎬 사용 시나리오

### 시나리오 1: 코드 블록 리뷰

```
개발자: /code review

봇:    리뷰할 코드를 첨부하거나 붙여넣어 주세요.
       옵션:
       • 코드 블록 직접 입력 (text)
       • 파일 첨부 (.py, .js, .ts 등)
       • GitHub PR URL

개발자: [Python 파일 첨부]
       특히 PII 처리 부분 봐주세요

봇:   🔍 코드 리뷰 중...

봇:   📋 Code Review #042

      [일반 리뷰]
      • 함수 복잡도 OK
      • 타입 힌트 누락 3곳: line 12, 45, 78
      • 예외 처리 일반: line 34에서 bare except 위험

      [🛡 Argos 특화 체크]
      ⚠️ HIGH — line 56: PII가 마스킹 없이 OpenAI API로 전송
      • 변경 전: client.completions.create(prompt=user_text)
      • 권장: 사전에 mask_pii(user_text) 적용 후 호출
      • 참조: Argos_Context.md § 4.2 "민감정보 처리 안전성"

      ⚠️ MED — line 89: 정규식이 false positive 위험
      • '주민번호:\s*\d{6}-\d{7}' 패턴이 'sample' 키워드 미제외
      • 권장: scanner_rules.py 35번 줄 패턴과 일관 유지

      [Action]
      1. mask_pii 호출 추가 (HIGH)
      2. false positive 패턴 보강 (MED)
```

### 시나리오 2: 단위 테스트 자동 생성

```
개발자: /code test
       [scanner_rules.py 첨부]

봇:   ⚙️ 테스트 생성 중...

봇:   📝 추천 테스트 케이스 (12개)

      [posit­ive cases]
      • 표준 주민번호 형식 → 탐지
      • 외국인등록번호 → 탐지
      • ...

      [negative cases — false positive 방지]
      • 'sample: 123456-1234567' → 탐지 안 함
      • 'mock_rrn = "..."' → 탐지 안 함
      • 학번·전화번호 등 유사 패턴 → 탐지 안 함

      [edge cases]
      • 공백 포함 ('123456 - 1234567') → 정책 결정 필요
      • 마스킹된 형태 ('123456-1******') → 탐지 안 함

      코드:
      ```python
      import pytest
      from scanner_rules import detect_rrn

      def test_detect_standard_rrn():
          assert detect_rrn("주민번호: 901231-1234567") is not None

      # ...
      ```
```

### 시나리오 3: KISA 가이드라인 정합성 체크

```
개발자: /code kisa
       기능 설명: "사용자가 PC 앱에서 파일을 선택하면
                 DoD 표준에 따라 3패스 덮어쓰기로 영구 삭제"

봇:   🔍 KISA·법령 정합성 분석...

봇:   📋 정합성 리포트

      [관련 법령·표준]
      • 개인정보보호법 제21조 (개인정보의 파기)
      • KISA 개인정보 안전성 확보조치 기준
      • DoD 5220.22-M (3패스 덮어쓰기)

      [확인 필요 사항]
      ✅ DoD 3패스: 0x00 → 0xFF → random
      ⚠️ 랜덤 시드: secrets.SystemRandom 또는 os.urandom 사용?
      ⚠️ 파기 후 검증: 마지막 패스 후 read 검증 단계 있나?
      ⚠️ 파기 로그: "언제, 무엇을, 누가" 감사 로그 기록 의무

      [Action]
      1. random 패스에 secrets 사용 확인
      2. 파기 검증 단계 추가
      3. 파기 이벤트 audit_log에 기록
```

---

## 🛠 빌드 스펙

### 디렉토리 구조

```
bots/code_sentinel/
├── pyproject.toml
├── Dockerfile
├── railway.toml
├── README.md
├── prompts/
│   ├── system_base.md
│   ├── review_general.md
│   ├── review_security.md
│   ├── test_generation.md
│   └── kisa_compliance.md
├── rules/
│   ├── argos_patterns.yaml      # Argos 코드베이스 알려진 안티패턴
│   ├── kisa_guidelines.yaml     # KISA 가이드라인 요약
│   └── pipa_articles.yaml       # 개인정보보호법 조항 매핑
└── src/code_sentinel/
    ├── __init__.py
    ├── main.py
    ├── commands.py
    ├── reviewer.py              # 리뷰 오케스트레이션
    ├── github_fetcher.py        # PR URL → 코드 가져오기
    ├── language_detector.py     # 코드 언어 자동 감지
    ├── rule_matcher.py          # YAML 규칙 매칭 (LLM 호출 전 1차)
    ├── escalator.py             # Haiku → Sonnet 자동 승급 판단
    └── ui.py
```

### 핵심 인터페이스

#### `reviewer.py` — 리뷰 메인

```python
class CodeReviewer:
    def __init__(self, llm: LLMRouter, argos: ArgosContext, rules_dir: str):
        self.llm = llm
        self.argos = argos
        self.argos_patterns = self._load_yaml("argos_patterns.yaml")
        self.escalator = Escalator()

    async def review(
        self,
        code: str,
        language: str,
        focus: ReviewFocus,
        user_id: str,
    ) -> ReviewResult:
        # 1. 룰베이스 1차 매칭 (저비용, LLM 호출 전)
        rule_findings = self.rule_matcher.match(code, self.argos_patterns)

        # 2. 복잡도·민감도 평가 → Haiku vs Sonnet 결정
        task_type = self.escalator.choose(code, rule_findings)

        # 3. LLM 호출
        request = LLMRequest(
            task_type=task_type,
            system=self._build_system_prompt(focus, rule_findings),
            messages=[{"role": "user", "content": code}],
            user_id=user_id,
            bot_name="code_sentinel",
            max_tokens=2000,
        )
        response = await self.llm.call(request)

        # 4. 응답 파싱 → 구조화 결과
        return self._parse_response(response, rule_findings)

    async def generate_tests(self, code: str, user_id: str) -> TestSuite: ...
    async def check_kisa(self, feature_description: str, user_id: str) -> ComplianceReport: ...
```

#### `rule_matcher.py` — 룰베이스 1차 검사

LLM 호출 전에 정규식·AST 기반으로 잡을 수 있는 건 미리 잡아 비용 절감.

```yaml
# rules/argos_patterns.yaml
patterns:
  - id: hardcoded_api_key
    severity: CRITICAL
    description: API 키 하드코딩
    regex: '(api_key|API_KEY|secret)\s*=\s*["\'][a-zA-Z0-9_\-]{20,}["\']'
    suggestion: 환경변수로 이동, .env로 관리

  - id: pii_to_external_api
    severity: HIGH
    description: PII가 마스킹 없이 외부 API 호출
    ast_pattern: |
      외부 API 호출 함수의 인자에 mask_pii() 호출이 없는 경우
    suggestion: mask_pii(user_text) 사전 적용

  - id: weak_random
    severity: MED
    description: 보안 컨텍스트에서 random.* 사용
    regex: '\brandom\.(random|randint|choice)\('
    context: dod_overwrite|key_generation|token
    suggestion: secrets 모듈 사용

  - id: bare_except
    severity: MED
    description: bare except 사용
    regex: '^\s*except\s*:'
    suggestion: 구체적 예외 명시

  - id: legacy_import
    severity: LOW
    description: src/legacy/ import
    regex: 'from\s+legacy\.'
    suggestion: 신규 모듈로 이전 검토
```

```python
class RuleMatcher:
    def match(self, code: str, patterns: list) -> list[Finding]:
        findings = []
        for pattern in patterns:
            if pattern.has_regex:
                findings.extend(self._match_regex(code, pattern))
            if pattern.has_ast:
                findings.extend(self._match_ast(code, pattern))
        return findings
```

#### `escalator.py` — 모델 자동 승급

```python
class Escalator:
    def choose(self, code: str, rule_findings: list[Finding]) -> TaskType:
        """
        간단한 코드 → Haiku
        다음 중 하나라도 만족하면 → Sonnet으로 승급:
        - CRITICAL/HIGH severity finding 있음
        - 코드 길이 > 300줄
        - 보안 관련 키워드 다수 (encrypt, decrypt, auth, token, password)
        - 사용자가 명시적으로 'security' focus 지정
        """
        if any(f.severity in ("CRITICAL", "HIGH") for f in rule_findings):
            return TaskType.CODE_REVIEW_COMPLEX
        if len(code.splitlines()) > 300:
            return TaskType.CODE_REVIEW_COMPLEX
        if self._has_security_keywords(code):
            return TaskType.CODE_REVIEW_COMPLEX
        return TaskType.CODE_REVIEW_SIMPLE
```

#### `github_fetcher.py` — PR URL 처리

```python
class GitHubFetcher:
    async def fetch_pr_diff(self, pr_url: str) -> PRContent:
        """
        https://github.com/secudeck/argos/pull/123 → diff + 변경 파일 내용
        GitHub API 사용 (PAT 필요), 토큰은 환경변수
        """
        ...
```

> **주의**: GitHub PAT은 read-only로 발급. private repo 접근 권한만, write 권한 없게.

### 슬래시 커맨드

```python
class CodeCommands(app_commands.Group):
    name = "code"
    description = "코드 리뷰 봇"

    @app_commands.command(description="코드 리뷰 + Argos 보안 체크")
    async def review(
        self,
        interaction: discord.Interaction,
        attachment: discord.Attachment | None = None,
        text: str | None = None,
        pr_url: str | None = None,
        focus: str | None = None,  # general | security | performance | tests
    ):
        ...

    @app_commands.command(description="단위 테스트 자동 생성")
    async def test(self, interaction: discord.Interaction, ...):
        ...

    @app_commands.command(description="KISA 가이드라인·법령 정합성 체크")
    async def kisa(self, interaction: discord.Interaction, feature: str):
        ...
```

---

## 💰 비용 예산 산정

### 단일 리뷰 비용

| 시나리오 | 모델 | 입력 토큰 | 출력 토큰 | 캐시 | 추정 비용 |
|---|---|---|---|---|---|
| 짧은 코드 (50줄) Haiku | Haiku 4.5 | 4,000 (캐시) + 500 | 800 | 4,000 | 약 80원 |
| 중간 코드 (200줄) Haiku | Haiku 4.5 | 4,000 (캐시) + 2,000 | 1,200 | 4,000 | 약 150원 |
| 긴 코드 / 보안 → Sonnet | Sonnet 4.5 | 4,000 (캐시) + 2,500 | 1,500 | 4,000 | 약 600원 |
| 테스트 생성 | Sonnet 4.5 | 4,000 + 1,500 | 2,000 | 4,000 | 약 700원 |
| KISA 체크 | Sonnet 4.5 | 4,000 + 500 | 1,500 | 4,000 | 약 500원 |

### 월 사용 시뮬레이션

- 개발자 3명 × 일 5회 × 22일 = 330회/월
- 70% Haiku (231회 × 평균 100원 = 23,100원)
- 30% Sonnet 자동 승급 (99회 × 평균 600원 = 59,400원)
- → 약 82,000원

> **예산 초과**: 60,000원 한도 초과 가능. 다음 중 하나로 조정:
> 1. 한도 80,000원으로 조정 (다른 봇 예산에서 차감)
> 2. 사용자별 일일 호출 5회 → 3회로 제한
> 3. Sonnet 승급 조건 더 엄격하게 (CRITICAL만)

---

## 🧪 테스트 전략

### 룰베이스 정확성

- 알려진 안티패턴 코드 샘플 15개 입력 → 모두 탐지되는지
- false positive 코드 샘플 (sample, mock 키워드 포함) → 탐지 안 되는지

### LLM 리뷰 품질

- Argos 실제 PR 5개를 입력 → 사람 리뷰어와 비교
- 핵심 지표: 보안 이슈 누락 0건 (false negative가 가장 위험)

### 비용 제어

- 1주일 dry-run 후 실제 비용 측정
- Sonnet 승급 비율이 30% 이내인지 확인 (초과 시 escalator 튜닝)

---

## ⚠️ 주의사항

### 1. 코드 유출 위험
개발자가 첨부한 코드는 외부 LLM(Anthropic, Google)으로 전송됨. **이건 Argos가 자기 모순에 빠질 수 있는 지점**:
- "PII는 외부 API에 보내지 마세요" 라고 가르치는 봇이 코드 자체를 외부 API로 보냄
- → 명시적 안내 필요: "이 봇은 코드를 LLM API로 전송합니다. 민감 코드는 직접 리뷰하세요."
- → Anthropic의 Zero Data Retention 정책 활용 권장 (엔터프라이즈 플랜)

### 2. PR URL 인증
private repo 접근하려면 GitHub PAT 필요. 봇 환경변수에만 보관, 절대 응답에 노출 X.

### 3. KISA 가이드라인 변경
법령·가이드라인은 주기적으로 업데이트됨. `rules/kisa_guidelines.yaml` 분기별 점검 일정 잡기.

### 4. 테스트 코드 정확성
LLM이 생성한 테스트 코드는 컴파일 오류·잘못된 어설션 가능. 사용자에게 "검토 후 사용" 안내.

---

## ✅ 완료 체크리스트

- [ ] `argos_patterns.yaml` 룰 10개 이상 정의
- [ ] `kisa_guidelines.yaml`, `pipa_articles.yaml` 작성
- [ ] `RuleMatcher` 단위 테스트: 알려진 안티패턴 100% 탐지
- [ ] `Escalator`: 보안 코드 100% Sonnet 승급
- [ ] 슬래시 커맨드 3종 (`review`, `test`, `kisa`) 동작
- [ ] PDF/MD/PY/TS/JS 파일 파싱 정상
- [ ] GitHub PR URL 입력 시 diff 가져오기 정상
- [ ] 평균 응답 시간: 짧은 코드 < 30초, 긴 코드 < 90초
- [ ] 1주일 dry-run 후 비용 추정치 ±20% 이내
- [ ] Argos 실제 PR 5개로 통합 테스트 통과 (보안 이슈 누락 0건)
- [ ] README에 "코드 외부 전송" 명시 안내

---

다음 문서: `04_INTERVIEW_COMPANION.md`
