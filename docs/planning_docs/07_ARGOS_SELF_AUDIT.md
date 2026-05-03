# 07. Argos Self-Audit — 자가 검증 봇 (마케팅 자산)

> **Phase**: 4
> **주 사용자**: 전원 (특히 개발팀, 자동 트리거 위주)
> **모델**: Claude Sonnet 4.5
> **예산**: 월 15,000원
> **빌드 기간 추정**: 2~3일

---

## 🎯 미션

**"Argos를 만드는 회사가 Argos로 자기를 검증한다"** — 마케팅 자산이 되는 봇.

8월 펜테스트·베타테스트 시점에 가동. Argos 코드베이스 자체를 자동 모니터링, 신규 기능의 컴플라이언스 정합성 자동 체크.

### Code Sentinel과 다른 점

- **Code Sentinel**: 사람이 코드 첨부하고 리뷰 요청 (능동)
- **Argos Self-Audit**: 자동 트리거 (수동)
  - 매일 새벽 cron: 알려진 보안 이슈 모니터링
  - GitHub webhook: PR 머지 시 자동 검토
  - 신규 기능 PRD 업로드 시 자동 컴플라이언스 체크

### 마케팅 활용

이 봇이 만들어내는 **자산**:
- 일일 보안 점검 리포트 (랜딩페이지에 "지난 30일간 0건 사고" 표시 가능)
- 신규 기능별 컴플라이언스 매핑 문서 (영업 자료)
- 자가 검증 사례 (블로그 포스트, "We dogfood Argos")

---

## 🎬 사용 시나리오

### 시나리오 1: 자동 일일 점검 (cron)

```
[매일 새벽 3시 자동 실행]

봇:   📋 Daily Self-Audit — 2026-09-15
      [#self-audit 채널에 자동 게시]

      [코드베이스 스캔 결과]
      ✅ 하드코딩된 시크릿: 0건
      ✅ PII 누출 패턴: 0건
      ✅ KISA 가이드라인 위반: 0건
      ⚠️ 레거시 코드 잔존: src/legacy/old_scanner.py
      ✅ 단위 테스트 커버리지: 78% (목표 80%)

      [의존성 보안]
      ⚠️ openai 1.x → 1.42 권장 (CVE-2025-XXXX)
      ✅ anthropic 최신
      ✅ pydantic 최신

      [지난 24시간 변경]
      • PR #142 머지 (api/scan endpoint)
        자동 검토 결과: ✅ 통과 (Code Sentinel)
        KISA 정합성: ✅ 통과

      [이번 주 트렌드]
      • 위반 0건 7일 연속 ✅
      • 신규 기능 PRD 3건 자동 검토 완료

      [Action]
      1. legacy/old_scanner.py 제거 일정 잡기
      2. openai SDK 업그레이드
```

### 시나리오 2: PR 자동 검토 (webhook)

```
[GitHub PR 머지 시 자동 트리거]

봇:   🔍 PR #143 자동 검토 — feature/encryption-v2
      [#self-audit 채널에 자동 게시]

      [Code Sentinel 위임 결과]
      ⚠️ MED — src/encryption/aes.py line 45
      • AES-256 모드 GCM이 아닌 CBC 사용
      • 권장: GCM 모드로 전환 (KISA 가이드)

      [컴플라이언스 매핑]
      이 PR이 영향 주는 영역:
      • 개인정보보호법 제29조 (안전성 확보 조치)
      • KISA 가이드 § 4.2 (암호화 알고리즘)

      [Self-Audit 결론]
      🔴 머지 차단 권장
      이유: 법령 준수 영역에서 권장 미준수.
      담당: @개발팀
```

### 시나리오 3: 신규 기능 컴플라이언스 매핑

```
대표: /audit feature
      [PRD 첨부: "사용자 활동 로그 90일 보관"]

봇:   📋 Feature Compliance Map

      [관련 법령·표준]
      • 개인정보보호법 제21조 (개인정보 파기)
      • 개인정보보호법 제29조 (안전성 확보)
      • 통신비밀보호법 제15조의2

      [요구사항 매핑]
      ✅ 보유 기간 명시 (90일) → 법 제15조 충족
      ⚠️ 자동 파기 메커니즘 필요 (90일 + 1초 자동 삭제)
      ⚠️ 파기 로그 보관 (감사 대비)
      ⚠️ 사용자 열람·삭제 요청 대응 절차
      ⚠️ 위탁자 통지 의무 (해당하는 경우)

      [구현 체크리스트]
      ☐ 90일 cron job 설정
      ☐ DoD 5220.22-M 또는 동급 파기
      ☐ audit_log 테이블 분리 보관 (10년)
      ☐ /api/user/data DELETE 엔드포인트
      ☐ 위탁자 통지 옵션 (선택)

      [위험 시나리오]
      🔴 90일 경과 데이터 자동 파기 실패 시 → 법 위반
      🔴 파기 후 백업에서 복구 시 → 파기 의무 위반

      [Argos 영업 활용]
      이 기능은 자체로 영업 무기:
      "Argos는 자기 활동 로그도 90일 자동 파기합니다.
       당신 회사도 이렇게 운영하실 수 있습니다."
```

---

## 🛠 빌드 스펙

### 디렉토리 구조

```
bots/argos_self_audit/
├── pyproject.toml
├── Dockerfile
├── railway.toml
├── README.md
├── prompts/
│   ├── daily_scan.md
│   ├── pr_review.md
│   └── feature_compliance.md
├── checks/
│   ├── secret_patterns.yaml         # 하드코딩 시크릿 패턴
│   ├── pii_patterns.yaml            # PII 누출 패턴
│   ├── kisa_checks.yaml             # KISA 가이드라인 체크
│   └── pipa_articles.yaml           # 개인정보보호법 조항
└── src/argos_self_audit/
    ├── __init__.py
    ├── main.py
    ├── commands.py
    ├── scheduler.py                 # cron 트리거
    ├── github_webhook.py            # PR 트리거
    ├── repo_scanner.py              # 코드베이스 스캔
    ├── dependency_checker.py        # CVE 체크
    ├── compliance_mapper.py         # PRD → 법령 매핑
    ├── reporter.py                  # 디스코드 리포트 생성
    └── ui.py
```

### 핵심 인터페이스

#### `scheduler.py`

```python
from discord.ext import tasks

class AuditScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_scan.start()

    @tasks.loop(time=time(hour=3, minute=0))  # 매일 03:00 KST
    async def daily_scan(self):
        result = await self.scanner.scan_all()
        report = self.reporter.daily(result)
        channel = self.bot.get_channel(SELF_AUDIT_CHANNEL_ID)
        await channel.send(embed=report.to_embed())
```

#### `repo_scanner.py`

```python
class RepoScanner:
    def __init__(self, repo_path: str, llm: LLMRouter):
        self.repo_path = repo_path
        self.llm = llm

    async def scan_all(self) -> ScanResult:
        # 1. 룰베이스 스캔 (LLM 호출 X)
        secret_findings = self._scan_secrets()
        pii_findings = self._scan_pii_patterns()
        legacy_findings = self._scan_legacy()
        coverage = self._test_coverage()

        # 2. 의존성 CVE
        cve_findings = await self.dep_checker.check()

        # 3. 지난 24시간 PR 검토 결과 집계
        pr_results = await self._aggregate_pr_reviews()

        return ScanResult(
            secret_findings=secret_findings,
            pii_findings=pii_findings,
            legacy_findings=legacy_findings,
            cve_findings=cve_findings,
            pr_results=pr_results,
            coverage=coverage,
        )

    def _scan_secrets(self) -> list[Finding]:
        """trufflehog, gitleaks 같은 패턴 사용. LLM 불필요."""
        ...
```

#### `github_webhook.py`

```python
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook/github")
async def github_webhook(request: Request):
    event = request.headers.get("X-GitHub-Event")
    payload = await request.json()

    if event == "pull_request" and payload["action"] == "closed" and payload["pull_request"]["merged"]:
        pr_url = payload["pull_request"]["html_url"]
        # Code Sentinel에 위임 (HTTP 호출)
        sentinel_result = await invoke_code_sentinel(pr_url)
        # 컴플라이언스 매핑 추가
        compliance_result = await compliance_mapper.map_pr(pr_url)
        # 디스코드 리포트
        report = reporter.pr_review(sentinel_result, compliance_result)
        await post_to_discord(report)

    return {"ok": True}
```

> Railway에서 봇 + 웹훅 서버 같이 띄우려면 별도 포트로 FastAPI uvicorn 실행. Procfile 또는 supervisord 사용.

#### `compliance_mapper.py`

```python
class ComplianceMapper:
    def __init__(self, llm: LLMRouter, articles_path: str, kisa_path: str):
        self.llm = llm
        self.articles = self._load_yaml(articles_path)
        self.kisa = self._load_yaml(kisa_path)

    async def map_feature(self, prd_text: str, user_id: str) -> ComplianceMap:
        """
        PRD 텍스트 → 관련 법령·표준 매핑.
        Sonnet 1회 호출 (구조화 추출).
        """
        ...
```

### 슬래시 커맨드

```python
class AuditCommands(app_commands.Group):
    name = "audit"

    @app_commands.command(description="즉시 코드베이스 스캔 실행")
    async def scan(self, interaction):
        ...

    @app_commands.command(description="신규 기능 컴플라이언스 매핑")
    async def feature(
        self,
        interaction,
        prd: discord.Attachment | None = None,
        text: str | None = None,
    ):
        ...

    @app_commands.command(description="이번 달 self-audit 종합 리포트")
    async def report(self, interaction):
        ...
```

### `checks/secret_patterns.yaml`

```yaml
patterns:
  - id: openai_key
    regex: 'sk-[a-zA-Z0-9]{48,}'
    severity: CRITICAL
  - id: anthropic_key
    regex: 'sk-ant-[a-zA-Z0-9\-]{90,}'
    severity: CRITICAL
  - id: aws_key
    regex: 'AKIA[0-9A-Z]{16}'
    severity: CRITICAL
  - id: github_token
    regex: 'ghp_[a-zA-Z0-9]{36}'
    severity: HIGH
  - id: hardcoded_password
    regex: '(password|passwd|pwd)\s*=\s*["''][^"'']{8,}["'']'
    severity: HIGH
```

---

## 💰 비용 예산 산정

| 동작 | 모델 | 빈도 | 1회 비용 | 월 비용 |
|---|---|---|---|---|
| 일일 스캔 (룰베이스) | LLM 호출 X | 30회/월 | 0원 | 0원 |
| 일일 리포트 생성 (LLM 종합) | Sonnet | 30회/월 | 약 200원 | 6,000원 |
| PR 자동 검토 (Code Sentinel 위임) | Sonnet | 약 30 PR/월 | 약 600원 | 18,000원 |
| Feature 컴플라이언스 매핑 | Sonnet | 5회/월 | 약 800원 | 4,000원 |

> PR 검토는 Code Sentinel 비용으로 잡힘. self-audit 자체 비용은 일일 + feature 매핑 = 약 10,000원/월.

---

## ⚠️ 주의사항

### 1. 코드베이스 외부 전송
봇이 Argos 소스코드를 LLM API로 전송. **모순 위험**:
- Argos가 "민감 정보 외부 전송 금지" 가르치는 도구인데 자기 코드를 외부로 보냄
- 대응: Anthropic Zero Data Retention 정책 적용 필수
- 또는: 룰베이스 검사만 하고 LLM 호출은 메타데이터·요약만

### 2. False Positive로 인한 신뢰 붕괴
봇이 매일 "0건 사고" 보고하다가 실제 사고 발생 시 신뢰 무너짐.
대응:
- 명시: "이 점검은 자동화된 1차 검사이며, 모든 사고를 잡지 못할 수 있습니다."
- 분기별 외부 펜테스트와 보완 (8월 펜테스트 일정 활용)

### 3. GitHub 토큰 권한
PR 정보 가져오려면 GitHub PAT 필요. **read-only**, write 권한 절대 없게.
Webhook 시크릿도 안전한 랜덤값.

### 4. 자동 게시 채널
`#self-audit` 전용 채널 생성. 일반 채널 도배 방지.
중요 알림(CRITICAL severity)은 `@개발팀` 멘션 추가.

### 5. 마케팅 자산화 시점
이 봇 결과를 외부 공개(블로그, 영업)할 때:
- 사고 사례까지 솔직히 공개 (투명성이 신뢰)
- "0건 사고" 자랑은 위험 (사고 나는 순간 무너짐)
- "지난 30일간 N건 발견·해결" 식으로 활동량 강조

---

## ✅ 완료 체크리스트

- [ ] `secret_patterns.yaml`, `pii_patterns.yaml`, `kisa_checks.yaml`, `pipa_articles.yaml` 작성
- [ ] 일일 cron 스케줄러 동작 (Railway scheduled job 또는 discord.py tasks)
- [ ] GitHub webhook 수신·처리 정상
- [ ] 룰베이스 스캔 정확도: 알려진 케이스 100% 탐지
- [ ] Code Sentinel HTTP 호출 통합 동작
- [ ] 슬래시 커맨드 3종 (`scan`, `feature`, `report`) 동작
- [ ] `#self-audit` 채널 생성·권한 설정
- [ ] CRITICAL 발견 시 멘션 알림 동작
- [ ] 응답 시간: 즉시 스캔 < 2분, feature 매핑 < 90초
- [ ] README + 마케팅 활용 가이드 문서화

---

다음 문서: `99_BUILD_ORDER.md`
