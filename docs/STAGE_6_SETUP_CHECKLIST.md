# Stage 6 — Argos Self-Audit 배포 전 사용자 체크리스트

> **상태**: 코드 작업 완료. 외부 인프라(Discord/GitHub/Railway) 설정은 사용자가 직접 처리해야 가동 가능.
> **정책**: 옵션 B 채택 — LLM 호출 0회, 룰베이스 + 키워드 매핑 + 템플릿 리포트로만 동작.
> **마지막 갱신**: 2026-05-04

---

## 0. 빠른 요약 (TL;DR)

| 영역 | 해야 할 일 | 예상 소요 |
|---|---|---|
| Discord | 봇 등록·서버 초대·채널 생성 | 15분 |
| GitHub | PAT 발급·웹훅 시크릿 생성·레포 URL 확정 | 10분 |
| Railway | 새 서비스 생성·환경변수 8종 주입·배포 | 20분 |
| GitHub Webhook | 배포 후 webhook URL 등록 | 5분 |
| 검증 | `/audit scan` 즉시 실행·결과 확인 | 10분 |

---

## 1. Discord 측

### 1-1. Argos Self-Audit 봇 등록

- [ ] [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**
  - 이름: `Argos Self-Audit` (또는 회사 톤에 맞춰)
  - Bot 탭에서 토큰 발급 → `.env` 의 `DISCORD_BOT_TOKEN_AUDIT` 에 저장
- [ ] **Privileged Gateway Intents** 켜기:
  - [x] `MESSAGE CONTENT INTENT` (cos 멘션 라우팅 전파에 필요할 수 있음)
- [ ] **OAuth2 → URL Generator** 에서 초대 URL 생성:
  - Scopes: `bot`, `applications.commands`
  - Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`, `Mention @everyone, @here, and All Roles`
- [ ] 생성된 URL 로 Secu Deck 서버에 봇 초대

### 1-2. `#self-audit` 채널 생성

- [ ] Secu Deck 서버에 `#self-audit` 텍스트 채널 추가
- [ ] 권한 설정:
  - 일반 멤버: **읽기만** 허용
  - Argos Self-Audit 봇: **메시지 보내기 + 임베드 링크** 허용
- [ ] 채널 우클릭 → **Copy Channel ID** → `.env` 의 `SELF_AUDIT_CHANNEL_ID`
  > ⚠️ 채널 ID 가 보이지 않으면 사용자 설정 → Advanced → Developer Mode 켜야 함.

### 1-3. CRITICAL 알림 역할 (선택)

- [ ] 서버 설정 → Roles → `@개발팀` (또는 동등 역할) 만들기
- [ ] 멤버 할당
- [ ] 역할 ID 복사 → `.env` 의 `SELF_AUDIT_DEV_ROLE_ID`
  > 이 값이 비어 있으면 CRITICAL 발견 시에도 멘션은 생략됨 (그래도 게시는 정상).

---

## 2. GitHub 측

### 2-1. read-only PAT 발급 (Argos Self-Audit 전용)

- [ ] [GitHub Settings → Developer settings → Personal access tokens (fine-grained)](https://github.com/settings/personal-access-tokens/new)
- [ ] 설정값:
  - Token name: `argos-self-audit-readonly`
  - Expiration: 90일 (만료 후 재발급 캘린더에 등록)
  - Repository access: **Only select repositories** → 감사 대상 Argos 레포만 선택
  - Permissions → Repository permissions:
    - `Contents`: **Read-only**
    - `Metadata`: **Read-only**
    - `Pull requests`: **Read-only** (PR 메타 조회용, 선택)
  - **그 외 모든 권한 None 으로**
- [ ] 발급된 토큰 → `.env` 의 `GITHUB_PAT_AUDIT`
  > ⚠️ 기존 `GITHUB_PAT` (Code Sentinel 용) 와 분리할 것. 한 토큰이 유출되어도 다른 봇은 안전하게.

### 2-2. 감사 대상 레포 URL 확정

- [ ] 어느 레포(들)을 감사할지 결정
  - 보통: Argos 메인 레포 1개 (예: `https://github.com/secu-deck/argos.git`)
  - 여러 레포 감사가 필요하면 봇을 여러 개 띄우거나 향후 멀티 레포 지원 추가
- [ ] HTTPS URL → `.env` 의 `ARGOS_REPO_URL`
  > 형식: `https://github.com/<owner>/<repo>.git` 끝에 `.git` 권장 (PAT 주입 호환).

### 2-3. Webhook 시크릿 생성

- [ ] 안전한 랜덤값 생성 (둘 중 하나):
  ```bash
  # macOS / Linux / Git Bash
  openssl rand -hex 32

  # PowerShell
  -join ((48..57) + (97..102) | Get-Random -Count 64 | % {[char]$_})
  ```
- [ ] 생성된 64자 hex → `.env` 의 `GITHUB_WEBHOOK_SECRET`
- [ ] 별도 보관 (Webhook 등록 시 GitHub 측에 같은 값 입력해야 함)

> Webhook URL 자체 등록은 **Railway 배포 이후**에 진행 (4-3 단계).

---

## 3. Railway 측

### 3-1. 새 서비스 생성

- [ ] Railway 프로젝트 → **New Service** → **GitHub Repo** → 모노레포 연결
- [ ] 서비스 이름: `argos-self-audit`
- [ ] **Settings → Build**
  - Builder: `Dockerfile`
  - Dockerfile Path: `bots/argos_self_audit/Dockerfile`
  - Watch Paths: `bots/argos_self_audit/**`, `packages/core/**`, `shared/**`
- [ ] **Settings → Networking → Generate Domain** 클릭 (외부에서 GitHub webhook 받기 위해 public URL 필요)
- [ ] **Settings → Internal Networking** 활성화 — cos 가 `BOT_URL_AUDIT` 으로 호출할 때 사용

### 3-2. 환경변수 주입

Railway 대시보드 **Variables** 탭에서 아래 키들을 입력. (`.env` 가 이미 채워져 있으면 그대로 복사)

| 키 | 값 출처 | 예시 |
|---|---|---|
| `DISCORD_BOT_TOKEN_AUDIT` | 1-1 단계 | `MTI...` |
| `SELF_AUDIT_CHANNEL_ID` | 1-2 단계 | `1234567890123456789` |
| `SELF_AUDIT_DEV_ROLE_ID` | 1-3 단계 (선택) | `9876543210987654321` |
| `GITHUB_PAT_AUDIT` | 2-1 단계 | `github_pat_...` |
| `ARGOS_REPO_URL` | 2-2 단계 | `https://github.com/secu-deck/argos.git` |
| `GITHUB_WEBHOOK_SECRET` | 2-3 단계 | (64자 hex) |
| `INTERNAL_API_SECRET` | 기존 5봇과 **동일값** | (기존 .env 참조) |
| `BOT_URL_CODE` | Code Sentinel internal URL | `http://code-sentinel.railway.internal:8080` |
| `DISCORD_GUILD_ID` | 기존 .env 참조 (선택) | `(서버 ID)` |
| `COST_MONTHLY_LIMIT_KRW_AUDIT` | (선택) | `15000` (LLM 0 이라 사실상 의미 없음) |
| `LOG_LEVEL` | (선택) | `INFO` |
| `AUDIT_RUN_ON_START` | (선택) | `1` (첫 배포 검증용. 안정 후 빈 값으로) |

### 3-3. cos 봇에 `BOT_URL_AUDIT` 추가

- [ ] Railway → **chief_of_staff 서비스** → Variables 탭
- [ ] 추가: `BOT_URL_AUDIT=http://argos-self-audit.railway.internal:8080`
- [ ] cos 서비스 재시작 (Variables 변경 시 자동 재시작 트리거됨)

### 3-4. 배포 트리거

- [ ] `main` 브랜치 push 또는 Railway 대시보드 **Deploy** 버튼
- [ ] Build 로그 확인 — `uv sync --no-dev` 가 끝까지 가는지
- [ ] Deploy 로그에서 `starting_argos_self_audit` 라인 보이면 성공

---

## 4. GitHub Webhook 등록

> Railway 가 public URL 을 발급한 뒤에 진행.

### 4-1. Webhook 추가

- [ ] 감사 대상 레포 → Settings → Webhooks → **Add webhook**
- [ ] 입력값:
  - Payload URL: `https://<railway-public-url>/webhook/github`
  - Content type: `application/json`
  - Secret: 2-3 단계에서 생성한 64자 hex
  - SSL verification: **Enable**
- [ ] **Which events?** → "Let me select individual events"
  - [x] `Pull requests`
  - 나머지 모두 해제
- [ ] **Active** 체크 → Add webhook

### 4-2. 등록 확인

- [ ] Webhook 페이지 → **Recent Deliveries** 탭
- [ ] `ping` 이벤트가 자동 발송됨 → Response: `200 OK` 와 `{"ok": true, "event": "ping"}` 확인
- [ ] 200 이 아니면:
  - 401: `GITHUB_WEBHOOK_SECRET` 불일치 → Railway/GitHub 양쪽 값 재확인
  - 503: Railway 환경변수 미주입 → `GITHUB_WEBHOOK_SECRET` 비어 있는지 확인
  - 404: Payload URL 의 `/webhook/github` 누락

---

## 5. 검증 (배포 후 실행)

### 5-1. 슬래시 커맨드 즉시 실행

- [ ] Secu Deck 서버 어느 채널에서나:
  - `/audit scan` — 즉시 룰베이스 스캔. 첫 실행은 git clone 시간 포함 1~2분 걸릴 수 있음.
  - `/audit feature text:사용자 활동 로그를 90일간 보관합니다` — 키워드 매핑 결과 확인
  - `/audit report` — 이번 달 누적 (첫 실행 시 0건)
- [ ] 결과가 `#self-audit` 채널이 아니라 호출한 채널에 ephemeral 로 뜨는지 확인 (정상)

### 5-2. cos 라우팅 검증

- [ ] cos 멘션으로 위임:
  - `@cos 자가 점검 한번 돌려봐` → `🛡 Argos Self-Audit` 으로 위임 확인
  - `@cos 사용자 데이터 90일 보관 기능 컴플라이언스 검토해줘` → audit_feature 라우팅 확인

### 5-3. PR 자동 검토 검증

- [ ] 감사 대상 레포에서 더미 PR 생성·머지
- [ ] `#self-audit` 채널에 자동 게시 확인 (수 초 내)
- [ ] GitHub Webhooks → Recent Deliveries 에서 200 응답 확인

### 5-4. 일일 cron 검증

- [ ] `AUDIT_RUN_ON_START=1` 로 부팅 → 즉시 1회 실행되어 `#self-audit` 채널에 게시되는지
- [ ] 검증 끝나면 `AUDIT_RUN_ON_START` 를 빈 값으로 두고 재배포 (운영 모드)
- [ ] 다음 날 03:00 KST 자동 게시 확인

---

## 6. 운영 메모

### 룰 추가/수정

- `bots/argos_self_audit/checks/*.yaml` 만 수정·커밋·푸시 → Railway 자동 재배포 → 다음 사이클부터 적용
- 봇 코드 변경 없이 룰만 갱신 가능 (mtime 자동 재로드)

### osv-scanner 활성화 (선택, 추천)

- 현재 Dockerfile 은 osv-scanner 미설치 → 의존성 CVE 검사는 자동으로 skip
- 활성화하려면 Dockerfile 에 추가:
  ```dockerfile
  RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc git curl \
      && curl -L https://github.com/google/osv-scanner/releases/latest/download/osv-scanner_linux_amd64 \
         -o /usr/local/bin/osv-scanner \
      && chmod +x /usr/local/bin/osv-scanner \
      && rm -rf /var/lib/apt/lists/*
  ```

### 마케팅 자산화 시 주의

- ❌ "지난 N 일간 0건 사고" 자랑 — 사고 발생 시 신뢰 무너짐
- ✅ "지난 N 일간 N건 발견·자체 해결" — 활동량 강조
- 분기별 외부 펜테스트(8월 예정) 결과와 함께 공개

### 비용

- LLM 호출 0 → Argos Self-Audit 자체 비용 0원
- PR webhook 의 Code Sentinel 위임 비용은 **Code Sentinel 예산**에 계상됨
- `COST_MONTHLY_LIMIT_KRW_AUDIT` 는 형식상 두지만 실제 도달 가능성 0

---

## 7. 트러블슈팅

| 증상 | 원인·해결 |
|---|---|
| 봇이 온라인이지만 슬래시 커맨드 안 보임 | `DISCORD_GUILD_ID` 설정 후 재시작. 글로벌 동기화는 최대 1시간. |
| `/audit scan` 첫 실행 타임아웃 | 큰 레포면 git clone 5분 초과. `--depth 1` 이미 적용됐으나 그래도 느리면 ARGOS_CLONE_DIR 을 영구 볼륨으로 |
| `#self-audit` 채널에 게시 안 됨 | 봇 권한 부족 (Send Messages / Embed Links). 채널 권한 재확인 |
| Webhook 401 | `GITHUB_WEBHOOK_SECRET` Railway/GitHub 값 불일치. 양쪽 동일하게 재설정 |
| Webhook 503 | Railway 에서 `GITHUB_WEBHOOK_SECRET` 환경변수 누락 |
| `git clone` 실패 | `GITHUB_PAT_AUDIT` 권한 부족. PAT 의 Contents: Read-only 권한 + 레포 선택 재확인 |
| osv-scanner skip | Dockerfile 에 osv-scanner 미설치 — 정상 동작 (의존성 검사만 N/A 로 표기됨) |

---

## 8. 진행 상태 (이 파일에 직접 체크하면서 진행)

- [ ] 1-1. Discord 봇 등록·토큰 발급
- [ ] 1-2. `#self-audit` 채널 생성·채널 ID 확보
- [ ] 1-3. (선택) 개발팀 역할 ID 확보
- [ ] 2-1. `GITHUB_PAT_AUDIT` 발급
- [ ] 2-2. `ARGOS_REPO_URL` 확정
- [ ] 2-3. `GITHUB_WEBHOOK_SECRET` 생성
- [ ] 3-1. Railway 새 서비스 생성·도메인 발급
- [ ] 3-2. Railway 환경변수 12종 주입
- [ ] 3-3. cos 서비스에 `BOT_URL_AUDIT` 추가
- [ ] 3-4. 첫 배포 성공 (`starting_argos_self_audit` 로그)
- [ ] 4-1. GitHub Webhook 등록 (Pull requests 만)
- [ ] 4-2. ping 이벤트 200 OK
- [ ] 5-1. `/audit scan` 동작 확인
- [ ] 5-2. cos `@cos 자가 점검` 라우팅 확인
- [ ] 5-3. 더미 PR 머지 → `#self-audit` 자동 게시 확인
- [ ] 5-4. 일일 cron 03:00 KST 게시 확인

---

## 참조

- 빌드 가이드: `docs/planning_docs/07_ARGOS_SELF_AUDIT.md`
- 전체 스테이지: `docs/planning_docs/99_BUILD_ORDER.md`
- 봇 README: `bots/argos_self_audit/README.md`
