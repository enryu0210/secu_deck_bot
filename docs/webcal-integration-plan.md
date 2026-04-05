# WebCal 구독 URL 연동 계획

SecuDeck 스케줄 봇의 일정 데이터를 Google Calendar, Apple Calendar, Outlook 등  
모든 캘린더 앱에서 자동 동기화할 수 있도록 WebCal 구독 URL 기능을 추가하는 계획서.

---

## 개요

### 왜 WebCal인가?

현재 봇은 Discord 슬래시 커맨드로만 일정을 조회할 수 있다.  
캘린더 앱에서 직접 확인하거나 알림을 받으려면 별도의 연동이 필요한데,  
WebCal(iCalendar) 방식은 **추가 인증 없이 URL 하나로** 모든 캘린더 앱과 호환된다.

| 비교 항목 | WebCal | Google Calendar API |
|---|---|---|
| 구현 난이도 | 쉬움 | 복잡 (OAuth2 필요) |
| 호환성 | 모든 캘린더 앱 | Google Calendar만 |
| 팀원 설정 | URL 구독 1번 | 개인 OAuth 인증 |
| 자동 동기화 | 앱 설정에 따라 주기적 갱신 | 실시간 가능 |

---

## 동작 원리

```
[일정 등록 / 수정 / 삭제]
      ↓  (Discord 슬래시 커맨드)
  SQLite DB (schedules.db)
      ↓  (HTTP GET 요청 시 실시간 조회)
  FastAPI 엔드포인트 → .ics 파일 반환
      ↑
  Google Calendar / Apple Calendar / Outlook
  (webcal://... URL 구독, 주기적으로 자동 갱신)
```

---

## 구현 계획

### 1단계 — HTTP 서버 추가 (`calendar_server.py`)

봇과 별도로 가벼운 HTTP 서버를 띄워 `.ics` 파일을 제공한다.  
`bot.py`와 동일한 프로세스에서 비동기로 실행하거나, 독립 프로세스로 분리 가능.

**사용 라이브러리**:
- `fastapi` + `uvicorn` — HTTP 엔드포인트
- `icalendar` — ICS 파일 생성

**엔드포인트 설계**:

```
GET /calendar/{guild_id}.ics
```

- `guild_id`: Discord 서버 ID (봇이 설치된 서버 식별자)
- 반환: `text/calendar` MIME 타입의 `.ics` 파일
- 인증: 없음 (URL을 아는 사람만 접근 — 보안 수준 허용 시) 또는 토큰 파라미터 추가 가능

**예시 URL**:
```
webcal://your-server.railway.app/calendar/123456789012345678.ics
```

---

### 2단계 — ICS 파일 생성 로직

`icalendar` 라이브러리로 DB의 일정 데이터를 ICS 포맷으로 변환한다.

**변환 매핑**:

| DB 컬럼 | ICS 필드 | 비고 |
|---|---|---|
| `title` | `SUMMARY` | 일정 제목 |
| `description` | `DESCRIPTION` | 상세 설명 |
| `date` + `time` | `DTSTART` | 시간 없으면 종일(All-day) 이벤트 |
| `created_at` | `DTSTAMP` | 생성 타임스탬프 |
| `id` + `guild_id` | `UID` | 고유 식별자 (수정/삭제 추적용) |

**종일 이벤트 처리**:  
`time`이 `NULL`인 경우 `DTSTART`를 날짜만(`DATE` 타입)으로 설정하면  
캘린더 앱에서 자동으로 종일 이벤트로 표시된다.

---

### 3단계 — 봇 커맨드 추가 (`/일정 캘린더`)

팀원이 쉽게 구독 URL을 얻을 수 있도록 Discord 커맨드를 추가한다.

```
/일정 캘린더
→ 현재 서버의 WebCal 구독 URL을 DM 또는 ephemeral 메시지로 안내
```

응답 메시지 예시:
```
📅 캘린더 구독 URL
아래 URL을 캘린더 앱에 등록하면 자동으로 일정이 동기화돼요.

🔗 webcal://your-server.railway.app/calendar/123456789.ics

📱 앱별 등록 방법:
• Google Calendar: 다른 캘린더 → URL로 추가
• Apple Calendar: 파일 → 새 캘린더 구독
• Outlook: 캘린더 추가 → 인터넷에서 구독
```

---

### 4단계 — Railway 배포 설정 수정

현재 `railway.toml`은 봇 프로세스만 실행한다.  
HTTP 서버도 함께 실행되도록 포트 설정 추가가 필요하다.

```toml
# railway.toml 수정 예시
[deploy]
startCommand = "python bot.py & uvicorn calendar_server:app --host 0.0.0.0 --port $PORT"
```

또는 `bot.py` 내부에서 `asyncio`로 uvicorn을 함께 실행하는 방식도 가능.

---

## 파일 구조 (구현 후)

```
SecuDeck-schedulebot/
├── bot.py                  # 기존 — 봇 진입점
├── database.py             # 기존 — SQLite CRUD
├── calendar_server.py      # 신규 — FastAPI + ICS 생성
├── commands/
│   ├── __init__.py
│   └── schedule_commands.py  # 수정 — /일정 캘린더 커맨드 추가
├── requirements.txt        # 수정 — fastapi, uvicorn, icalendar 추가
└── railway.toml            # 수정 — 포트 설정 추가
```

---

## 추가 고려사항

### 보안
- Guild ID가 URL에 노출되므로 URL 자체가 접근 키 역할을 한다.
- 민감한 일정이 있다면 `?token=xxx` 쿼리 파라미터로 추가 인증 레이어 구현 권장.

### 동기화 주기
- Google Calendar는 기본 약 24시간마다 갱신 (강제 갱신 불가).
- Apple Calendar는 설정에서 갱신 주기 조정 가능 (최소 5분).
- 실시간 반영이 필요하다면 Google Calendar API 직접 연동 방식으로 전환해야 한다.

### 타임존
- 현재 DB는 타임존 정보 없이 `date`/`time`을 저장한다.
- ICS 생성 시 `TZID=Asia/Seoul`을 명시해야 캘린더 앱에서 올바른 시간대로 표시된다.
