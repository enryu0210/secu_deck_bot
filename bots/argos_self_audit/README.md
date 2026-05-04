# Argos Self-Audit (Phase 4)

> "Argos를 만드는 회사가 Argos로 자기를 검증한다" — 마케팅 자산이 되는 자가 검증 봇.

## 무엇을 하는가

| 트리거 | 동작 | 비용 |
|---|---|---|
| 매일 03:00 KST cron | Argos 레포 룰베이스 스캔 → `#self-audit` 채널 자동 게시 | 0원 (LLM 호출 X) |
| GitHub PR merge webhook | Code Sentinel 에 위임 + 룰베이스 컴플라이언스 매핑 | Code Sentinel 비용에 합산 |
| `/audit scan` 슬래시 | 즉시 룰베이스 스캔 | 0원 |
| `/audit feature` 슬래시 | PRD 텍스트 → 키워드 기반 법령 매핑 | 0원 |
| `/audit report` 슬래시 | 이번 달 self-audit 종합 리포트 | 0원 |

**이 봇은 LLM API 를 호출하지 않습니다.** Argos 가 "민감 정보 외부 전송 금지" 를 가르치는 도구이기 때문에 자기 코드를 외부 LLM 에 보내지 않는 정책(옵션 B). 모든 검사는 룰베이스(정규식) 와 키워드 매핑·템플릿으로 수행한다. PR 자동 검토는 Code Sentinel 에 HTTP 위임하므로, 외부 전송 결정권은 PR 작성자가 갖는다.

## 환경변수

| 키 | 필수 | 설명 |
|---|---|---|
| `DISCORD_BOT_TOKEN_AUDIT` | ✅ | 디스코드 봇 토큰 |
| `INTERNAL_API_SECRET` | ✅ | 5봇 공통 — cos 위임 + Code Sentinel 호출 인증 |
| `BOT_URL_CODE` | ✅ | Code Sentinel internal API URL (PR 자동 검토 위임용) |
| `SELF_AUDIT_CHANNEL_ID` | ✅ | 일일 스캔/PR 결과 자동 게시 채널 ID |
| `SELF_AUDIT_DEV_ROLE_ID` | 선택 | CRITICAL 발견 시 멘션할 역할 ID |
| `ARGOS_REPO_URL` | ✅ | 감사 대상 레포 URL (ex. `https://github.com/secu-deck/argos.git`) |
| `GITHUB_PAT_AUDIT` | ✅ | read-only PAT — repo clone + PR 메타 조회용 |
| `GITHUB_WEBHOOK_SECRET` | ✅ | GitHub webhook HMAC 시크릿 |
| `DISCORD_GUILD_ID` | 선택 | 슬래시 커맨드 즉시 동기화 (개발용) |
| `COST_MONTHLY_LIMIT_KRW_AUDIT` | 선택 | 월 한도 (LLM 호출 없으므로 사실상 0, 기본 50000) |

## 검사 룰

`checks/*.yaml` 4종:
- `secret_patterns.yaml` — 하드코딩 시크릿 (OpenAI/Anthropic/AWS/GitHub/일반 비밀번호)
- `pii_patterns.yaml` — 한국 PII (주민번호·전화번호·계좌번호·이메일 누출 패턴)
- `kisa_checks.yaml` — KISA 가이드라인 핵심 항목 (암호화 모드·취약 알고리즘·HTTPS 강제 등)
- `pipa_articles.yaml` — 개인정보보호법 주요 조항 키워드 매핑

## 운영 메모

- 일일 스캔 결과는 **요약**만 디스코드 게시. 상세 finding 은 로그(structlog) 로만 남김.
- 룰 추가는 YAML 만 갱신하면 됨 (mtime 감지로 봇 재시작 없이 다음 사이클부터 적용).
- Webhook 검증은 GitHub `X-Hub-Signature-256` HMAC-SHA256.

## 마케팅 활용 가이드

- **하지 말 것**: "지난 N 일간 0건 사고" 자랑. 사고 나는 순간 신뢰가 무너진다.
- **할 것**: "지난 N 일간 N건 발견·자체 해결" 식 활동량 강조. 분기별 외부 펜테스트 결과와 함께 공개.
- 블로그 포스트 소재: "We dogfood Argos — and here's what it found this month."
