# `.env` 환경변수 설정 가이드

> Secu Deck 봇 6종(`pitch_sharpener`, `code_sentinel`, `interview_companion`, `design_echo`, `chief_of_staff`, `argos_self_audit`) 에 필요한 환경변수 전체 목록.
> **✍ 표시 = 수기 작업이 필요한 항목** (토큰 발급·ID 복사·시크릿 직접 생성).

---

## 1) 공통 / 인프라 (모든 봇 공유)

| 키 | 필수 | 어떻게 채우나 |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | ✍ console.anthropic.com 에서 발급. cos·pitch·code·interview·design 5봇이 공유 |
| `GOOGLE_API_KEY` | ✅ | ✍ aistudio.google.com 에서 Gemini API 키 발급. interview·design 가 사용 |
| `INTERNAL_API_SECRET` | ✅ | ✍ **5봇 공통값** — `openssl rand -hex 32` 같은 걸로 한 번만 생성해 전 봇에 동일하게 |
| `DATABASE_URL` | ⚠️ | Railway Postgres 가 자동 주입. 로컬 개발은 미설정 시 in-memory 폴백 (interview_companion 만 실사용) |
| `DISCORD_GUILD_ID` | 선택 | ✍ 개발 중 슬래시 즉시 동기화용 길드 ID (Discord 개발자 모드 → 서버 우클릭 → ID 복사) |
| `ARGOS_CONTEXT_PATH` | 선택 | `shared/Argos_Context.md` 같은 경로. 미설정 시 기본 탐색 경로 사용 |
| `LOG_LEVEL` | 선택 | 기본 `INFO`. 디버깅 시 `DEBUG` |

---

## 2) Pitch Sharpener (`bots/pitch_sharpener`)

| 키 | 필수 | 비고 |
|---|---|---|
| `DISCORD_BOT_TOKEN_PITCH` | ✅ | ✍ Discord 개발자 포털에서 봇 토큰 발급 |
| `COST_MONTHLY_LIMIT_KRW_PITCH` | 선택 | 기본 50,000 |

---

## 3) Code Sentinel (`bots/code_sentinel`)

| 키 | 필수 | 비고 |
|---|---|---|
| `DISCORD_BOT_TOKEN_CODE` | ✅ | ✍ Discord 봇 토큰 |
| `GITHUB_PAT` | 선택 | ✍ PR URL 리뷰 사용 시 read-only PAT |
| `COST_MONTHLY_LIMIT_KRW_CODE` | 선택 | 기본 50,000 |

---

## 4) Interview Companion (`bots/interview_companion`)

| 키 | 필수 | 비고 |
|---|---|---|
| `DISCORD_BOT_TOKEN_INTERVIEW` | ✅ | ✍ Discord 봇 토큰 |
| `COST_MONTHLY_LIMIT_KRW_INTERVIEW` | 선택 | 기본 50,000 |
| (`DATABASE_URL`) | ⚠️ | 위 공통 — 없으면 재시작 시 인터뷰 데이터 소실 |

---

## 5) Design Echo (`bots/design_echo`)

| 키 | 필수 | 비고 |
|---|---|---|
| `DISCORD_BOT_TOKEN_DESIGN` | ✅ | ✍ Discord 봇 토큰 |
| `COST_MONTHLY_LIMIT_KRW_DESIGN` | 선택 | 기본 50,000 |

---

## 6) Chief of Staff (`bots/chief_of_staff`)

| 키 | 필수 | 비고 |
|---|---|---|
| `DISCORD_BOT_TOKEN_COS` | ✅ | ✍ Discord 봇 토큰 |
| `BOT_URL_PITCH` | ✅ | 로컬: `http://localhost:<port>` / Railway: `http://pitch-sharpener.railway.internal:8080` |
| `BOT_URL_CODE` | ✅ | 동일 패턴 |
| `BOT_URL_INTERVIEW` | ✅ | 동일 패턴 |
| `BOT_URL_DESIGN` | ✅ | 동일 패턴 |
| `BOT_URL_AUDIT` | 선택 | Stage 6 도입 후 |
| `COST_MONTHLY_LIMIT_KRW_COS` | 선택 | 기본 30,000 |

---

## 7) Argos Self-Audit (`bots/argos_self_audit`)

| 키 | 필수 | 비고 |
|---|---|---|
| `DISCORD_BOT_TOKEN_AUDIT` | ✅ | ✍ Discord 봇 토큰 |
| `BOT_URL_CODE` | ✅ | Code Sentinel internal URL (PR 위임용) — cos 와 동일값 |
| `ARGOS_REPO_URL` | ✅ | ✍ 감사 대상 레포 URL (예: `https://github.com/secu-deck/argos.git`) |
| `GITHUB_PAT_AUDIT` | ✅ | ✍ read-only PAT (repo clone + PR 메타 조회용) |
| `GITHUB_WEBHOOK_SECRET` | ✅ | ✍ GitHub webhook HMAC 시크릿 (직접 생성 후 GitHub 측에도 동일하게 등록) |
| `SELF_AUDIT_CHANNEL_ID` | ✅ | ✍ 자동 게시 채널 ID (Discord 개발자 모드 → 채널 우클릭 → ID 복사) |
| `SELF_AUDIT_DEV_ROLE_ID` | 선택 | ✍ CRITICAL 시 멘션할 역할 ID |
| `ARGOS_CLONE_DIR` | 선택 | 미설정 시 기본 임시 경로 |
| `AUDIT_RUN_ON_START` | 선택 | `1`/`true` 면 부팅 직후 1회 스캔 |
| `COST_MONTHLY_LIMIT_KRW_AUDIT` | 선택 | LLM 호출 0원이라 사실상 무의미. 기본 50,000 |

---

## 8) Railway / 운영 전용 (Railway 가 자동 주입 — 직접 안 채워도 됨)

| 키 | 비고 |
|---|---|
| `PORT` | Railway 자동 주입. `InternalAPIServer` 가 자동 인식 |
| `INTERNAL_API_PORT` | `PORT` 가 없을 때 폴백 (기본 8080) |
| `UVICORN_LOG_LEVEL` | 기본 `warning` |

---

## 봇 추가/배포 시 꼭 기억할 3가지

1. **`INTERNAL_API_SECRET` 는 5봇 공통값** — 다르면 cos 의 모든 위임이 401 로 거부됩니다. Railway 환경별로 따로 두지 말고 한 번 정해서 전 서비스에 같은 값을 붙이세요.
2. **`BOT_URL_*` 는 로컬과 Railway 에서 형식이 다릅니다.** 로컬은 `http://localhost:<포트>`, Railway 는 `http://<service-name>.railway.internal:8080` (내부망). cos·argos_self_audit 둘 다 동일 값을 참조합니다.
3. **`DATABASE_URL` 누락 시 interview_companion 은 부팅은 되지만 in-memory 저장**입니다. 재시작 = 데이터 소실. 실사용 전 반드시 Railway Postgres 연결.

---

## 빠른 체크리스트 (수기 작업 항목만)

배포 전 ✍ 항목을 모두 채웠는지 확인:

- [ ] `ANTHROPIC_API_KEY` 발급
- [ ] `GOOGLE_API_KEY` 발급
- [ ] `INTERNAL_API_SECRET` 생성 → 5봇에 동일하게 주입
- [ ] `DISCORD_BOT_TOKEN_PITCH` / `_CODE` / `_INTERVIEW` / `_DESIGN` / `_COS` / `_AUDIT` 6개 봇 토큰
- [ ] `DISCORD_GUILD_ID` (개발용)
- [ ] `BOT_URL_PITCH` / `_CODE` / `_INTERVIEW` / `_DESIGN` (cos 용)
- [ ] `ARGOS_REPO_URL` + `GITHUB_PAT_AUDIT` + `GITHUB_WEBHOOK_SECRET` (argos_self_audit)
- [ ] `SELF_AUDIT_CHANNEL_ID` (argos_self_audit)
- [ ] `DATABASE_URL` (interview_companion 실사용 시)
