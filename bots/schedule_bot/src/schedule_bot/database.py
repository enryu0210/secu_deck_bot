"""SQLite 일정 저장소.

설계 메모:
- 외부 DB 의존성 없이 파일 1개로 영속. Railway 배포 시 Volume 마운트 + ``SCHEDULE_DB_PATH``
  환경변수로 영구 경로 지정 권장 (컨테이너 재시작 시 데이터 손실 방지).
- 모든 함수는 동기. SQLite 자체가 빠르고 봇 트래픽 규모가 작아 별도 async wrapper 불필요.
- ``guild_id`` 는 항상 함께 다닌다 — 다른 서버 일정이 섞여 보이면 사고. WHERE 절에 반드시 포함.
- ``conn.row_factory = sqlite3.Row`` 로 dict-like 접근. 호출자가 dict 로 변환해 반환받음.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path


# DB 파일 경로 — 환경변수 우선, 없으면 패키지 디렉토리(개발 편의).
# Railway 배포 시 Volume 경로(예: /app/data/schedules.db) 를 env 로 주입.
def _default_db_path() -> str:
    env = os.getenv("SCHEDULE_DB_PATH")
    if env:
        return env
    # 패키지 디렉토리의 상위(bot 루트) 에 둠 — 컨테이너 안에선 bots/schedule_bot/
    bot_root = Path(__file__).resolve().parents[2]
    return str(bot_root / "schedules.db")


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """DB 커넥션. row_factory 설정으로 dict 변환을 호출부에서 자연스럽게."""
    path = db_path or _default_db_path()
    # parent 디렉토리가 없으면 미리 생성 — Railway Volume 첫 부팅 대비.
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | None = None) -> None:
    """봇 부팅 시 1회 실행. 테이블이 없으면 생성."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # 일정 테이블 — guild_id 로 서버 분리, remind_sent 로 알림 중복 방지.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id    TEXT    NOT NULL,
            title       TEXT    NOT NULL,
            description TEXT,
            date        TEXT    NOT NULL,   -- YYYY-MM-DD
            time        TEXT,               -- HH:MM (선택)
            created_by  TEXT    NOT NULL,
            created_at  TEXT    NOT NULL,   -- ISO 8601
            remind_sent INTEGER DEFAULT 0
        )
    """)

    # 서버별 설정 — 알림 채널 1개씩.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id            TEXT PRIMARY KEY,
            reminder_channel_id TEXT
        )
    """)

    conn.commit()
    conn.close()


# ─────────────────── 일정 CRUD ───────────────────

def add_schedule(
    guild_id: str,
    title: str,
    date: str,
    time: str | None,
    description: str | None,
    created_by: str,
    db_path: str | None = None,
) -> int:
    """새 일정 INSERT. 생성된 ID 반환."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO schedules (guild_id, title, description, date, time, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (guild_id, title, description, date, time, created_by, datetime.now().isoformat()),
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return int(new_id)


def get_schedules_by_date(guild_id: str, date: str, db_path: str | None = None) -> list[dict]:
    """특정 날짜 일정 — 시간순 (NULL 은 뒤로)."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM schedules
        WHERE guild_id = ? AND date = ?
        ORDER BY (time IS NULL), time ASC, id ASC
        """,
        (guild_id, date),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_schedules_between(
    guild_id: str,
    start_date: str,
    end_date: str,
    db_path: str | None = None,
) -> list[dict]:
    """기간 일정 — 날짜·시간순."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM schedules
        WHERE guild_id = ? AND date BETWEEN ? AND ?
        ORDER BY date ASC, (time IS NULL), time ASC, id ASC
        """,
        (guild_id, start_date, end_date),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_upcoming_schedules(
    guild_id: str,
    limit: int = 10,
    db_path: str | None = None,
) -> list[dict]:
    """오늘 이후 최대 N건 (limit 안전 캡: 50)."""
    today = datetime.now().strftime("%Y-%m-%d")
    safe_limit = max(1, min(int(limit), 50))
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM schedules
        WHERE guild_id = ? AND date >= ?
        ORDER BY date ASC, (time IS NULL), time ASC, id ASC
        LIMIT ?
        """,
        (guild_id, today, safe_limit),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_schedule_by_id(
    schedule_id: int,
    guild_id: str,
    db_path: str | None = None,
) -> dict | None:
    """ID 조회 — guild_id 까지 일치해야 반환 (다른 서버 데이터 차단)."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM schedules WHERE id = ? AND guild_id = ?",
        (schedule_id, guild_id),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_schedule(
    schedule_id: int,
    guild_id: str,
    db_path: str | None = None,
    **fields,
) -> bool:
    """허용 필드만 UPDATE. 컬럼 이름은 화이트리스트로 강제 (SQL injection 차단)."""
    allowed = {"title", "description", "date", "time"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [schedule_id, guild_id]

    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE schedules SET {set_clause} WHERE id = ? AND guild_id = ?",
        values,
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def delete_schedule(schedule_id: int, guild_id: str, db_path: str | None = None) -> bool:
    """일정 삭제. guild_id 미일치 시 0건 → False."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM schedules WHERE id = ? AND guild_id = ?",
        (schedule_id, guild_id),
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


# ─────────────────── 알림 ───────────────────

def get_pending_reminders(
    target_date: str,
    target_time: str,
    db_path: str | None = None,
) -> list[dict]:
    """30분 전 알림 대상 — date·time 정확히 일치 + 아직 발송 안 됨 + 알림 채널 등록 길드."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT s.*, gs.reminder_channel_id
        FROM schedules s
        JOIN guild_settings gs ON s.guild_id = gs.guild_id
        WHERE s.date = ? AND s.time = ? AND s.remind_sent = 0
          AND gs.reminder_channel_id IS NOT NULL
        """,
        (target_date, target_time),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def mark_reminder_sent(schedule_id: int, db_path: str | None = None) -> None:
    """알림 발송 완료 표시 — 중복 발송 방지."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE schedules SET remind_sent = 1 WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()


# ─────────────────── 서버 설정 ───────────────────

def set_reminder_channel(guild_id: str, channel_id: str, db_path: str | None = None) -> None:
    """길드별 알림 채널 ID UPSERT."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO guild_settings (guild_id, reminder_channel_id)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET reminder_channel_id = excluded.reminder_channel_id
        """,
        (guild_id, channel_id),
    )
    conn.commit()
    conn.close()


def get_reminder_channel(guild_id: str, db_path: str | None = None) -> str | None:
    """길드 알림 채널 ID 조회. 미설정 None."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT reminder_channel_id FROM guild_settings WHERE guild_id = ?",
        (guild_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row["reminder_channel_id"] if row else None


__all__ = [
    "init_db",
    "get_connection",
    "add_schedule",
    "get_schedules_by_date",
    "get_schedules_between",
    "get_upcoming_schedules",
    "get_schedule_by_id",
    "update_schedule",
    "delete_schedule",
    "get_pending_reminders",
    "mark_reminder_sent",
    "set_reminder_channel",
    "get_reminder_channel",
]
