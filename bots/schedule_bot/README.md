# Schedule Bot

> 팀 일정 등록·조회·30분 전 자동 알림. LLM 호출 없음 (옵션 B).

## 무엇을 하는가

| 트리거 | 동작 | 비용 |
|---|---|---|
| `/일정 등록` 슬래시 | 새 일정을 SQLite 에 저장 | 0원 |
| `/일정 오늘 / 이번주 / 목록 / 날짜검색 / 상세` | 일정 조회 임베드 | 0원 |
| `/일정 수정 / 삭제` | ID 로 일정 조작 | 0원 |
| `/일정 알림채널` | 30분 전 알림 채널 지정 (관리자) | 0원 |
| 매 1분 백그라운드 | 30분 후 시작 일정 → 알림 채널에 임베드 발송 | 0원 |
| cos 위임 `/api/invoke` | 자연어 → 조회/등록 위임 (5개 액션) | 0원 |

**LLM 호출 없음.** 모든 결정은 SQLite + discord.py 로직만으로 이뤄진다.

## 환경변수

| 키 | 필수 | 설명 |
|---|---|---|
| `DISCORD_BOT_TOKEN_SCHEDULE` | ✅ | 디스코드 봇 토큰 |
| `INTERNAL_API_SECRET` | ✅ | 5봇 공통 — cos 위임 인증 |
| `SCHEDULE_DB_PATH` | 선택 | SQLite 파일 경로 (기본 `<bot_dir>/schedules.db`). Railway 에서는 Volume 경로 권장. |
| `DISCORD_GUILD_ID` | 선택 | 슬래시 커맨드 즉시 동기화 (개발용) |
| `COST_MONTHLY_LIMIT_KRW_SCHEDULE` | 선택 | 월 한도 (LLM 미호출로 사실상 0, 기본 50000) |
| `PORT` / `INTERNAL_API_PORT` | 선택 | 내부 API 포트 (Railway 가 PORT 자동 주입) |

## cos 위임 액션

| action | payload | 반환 요약 |
|---|---|---|
| `schedule_today` | `{guild_id}` | 오늘 등록된 일정 목록 |
| `schedule_week` | `{guild_id}` | 이번 주 (오늘 ~ 일요일) 일정 목록 |
| `schedule_upcoming` | `{guild_id, limit?}` | 다가오는 일정 최대 10건 |
| `schedule_search` | `{guild_id, date}` | 특정 날짜(YYYY-MM-DD) 일정 |
| `schedule_register` | `{guild_id, title, date, time?, description?, created_by?}` | 등록 결과 |

`guild_id` 는 cos 의 delegator 가 디스코드 메시지에서 자동 주입한다.

## 운영 메모

- SQLite 파일은 컨테이너 재시작 시 사라진다 — Railway Volume 마운트 권장.
- 알림 발송 권한 없으면 조용히 스킵 (무한 재시도 방지).
- 슬래시 그룹명은 `/일정` 그대로 유지.

## 마이그레이션 노트

이 봇은 원래 저장소 루트의 `SecuDeck-schedulebot/` 디렉토리에 있었다. 표준 봇 패턴(SecuDeckBot/InternalAPIServer/uv 워크스페이스) 으로 이관했고, cos 위임이 가능해진 것이 가장 큰 차이.
