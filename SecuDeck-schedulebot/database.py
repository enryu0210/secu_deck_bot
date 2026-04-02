"""
database.py
데이터베이스 초기화 및 CRUD 로직을 담당하는 모듈.
SQLite를 사용해 외부 DB 없이 파일 하나로 데이터를 영속 저장한다.
"""

import sqlite3
import os
from datetime import datetime

# DB 파일 경로 (봇과 같은 디렉토리에 저장)
DB_PATH = os.path.join(os.path.dirname(__file__), "schedules.db")


def get_connection():
    """DB 연결 반환. Row를 dict처럼 접근 가능하도록 row_factory 설정."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    애플리케이션 시작 시 최초 1회 실행.
    테이블이 없으면 생성하고, 있으면 그냥 넘어간다.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 일정 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id    TEXT    NOT NULL,
            title       TEXT    NOT NULL,
            description TEXT,
            date        TEXT    NOT NULL,   -- YYYY-MM-DD
            time        TEXT,               -- HH:MM (선택)
            created_by  TEXT    NOT NULL,   -- 등록자 닉네임#태그
            created_at  TEXT    NOT NULL,   -- ISO 8601
            remind_sent INTEGER DEFAULT 0   -- 30분 전 알림 발송 여부 (0/1)
        )
    """)

    # 서버별 설정 테이블 (알림 채널 등)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id           TEXT PRIMARY KEY,
            reminder_channel_id TEXT
        )
    """)

    conn.commit()
    conn.close()


# ─────────────────── 일정 CRUD ───────────────────

def add_schedule(guild_id: str, title: str, date: str, time: str | None,
                 description: str | None, created_by: str) -> int:
    """
    새 일정을 DB에 삽입하고 생성된 ID를 반환한다.
    - date: 'YYYY-MM-DD' 형식 문자열
    - time: 'HH:MM' 형식 문자열 또는 None
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO schedules (guild_id, title, description, date, time, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (guild_id, title, description, date, time, created_by,
          datetime.now().isoformat()))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def get_schedules_by_date(guild_id: str, date: str) -> list:
    """특정 날짜의 일정 목록을 시간순으로 반환한다."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM schedules
        WHERE guild_id = ? AND date = ?
        ORDER BY time ASC NULLS LAST, id ASC
    """, (guild_id, date))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_schedules_between(guild_id: str, start_date: str, end_date: str) -> list:
    """시작일 ~ 종료일 사이의 모든 일정을 날짜·시간순으로 반환한다."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM schedules
        WHERE guild_id = ? AND date BETWEEN ? AND ?
        ORDER BY date ASC, time ASC NULLS LAST, id ASC
    """, (guild_id, start_date, end_date))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_upcoming_schedules(guild_id: str, limit: int = 10) -> list:
    """오늘 이후의 예정된 일정을 최대 limit개 반환한다."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM schedules
        WHERE guild_id = ? AND date >= ?
        ORDER BY date ASC, time ASC NULLS LAST, id ASC
        LIMIT ?
    """, (guild_id, today, limit))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_schedule_by_id(schedule_id: int, guild_id: str) -> dict | None:
    """ID로 특정 일정 1건을 조회한다. 해당 서버 소속인지 검증 포함."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM schedules WHERE id = ? AND guild_id = ?
    """, (schedule_id, guild_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_schedule(schedule_id: int, guild_id: str, **fields) -> bool:
    """
    지정된 필드만 업데이트한다.
    수정 가능한 필드: title, description, date, time
    """
    allowed = {"title", "description", "date", "time"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [schedule_id, guild_id]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        UPDATE schedules SET {set_clause}
        WHERE id = ? AND guild_id = ?
    """, values)
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def delete_schedule(schedule_id: int, guild_id: str) -> bool:
    """ID로 일정을 삭제하고 성공 여부를 반환한다."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM schedules WHERE id = ? AND guild_id = ?
    """, (schedule_id, guild_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


# ─────────────────── 알림 관련 ───────────────────

def get_pending_reminders(target_date: str, target_time: str) -> list:
    """
    알림 발송이 안 된 일정 중, 지정된 날짜·시간에 해당하는 것을 반환한다.
    (30분 전 알림 태스크에서 사용)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, gs.reminder_channel_id
        FROM schedules s
        JOIN guild_settings gs ON s.guild_id = gs.guild_id
        WHERE s.date = ? AND s.time = ? AND s.remind_sent = 0
          AND gs.reminder_channel_id IS NOT NULL
    """, (target_date, target_time))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def mark_reminder_sent(schedule_id: int):
    """알림 발송 완료 표시."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE schedules SET remind_sent = 1 WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()


# ─────────────────── 서버 설정 ───────────────────

def set_reminder_channel(guild_id: str, channel_id: str):
    """알림을 보낼 채널 ID를 저장한다. 없으면 삽입, 있으면 업데이트."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO guild_settings (guild_id, reminder_channel_id)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET reminder_channel_id = excluded.reminder_channel_id
    """, (guild_id, channel_id))
    conn.commit()
    conn.close()


def get_reminder_channel(guild_id: str) -> str | None:
    """설정된 알림 채널 ID를 반환한다. 미설정 시 None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT reminder_channel_id FROM guild_settings WHERE guild_id = ?
    """, (guild_id,))
    row = cursor.fetchone()
    conn.close()
    return row["reminder_channel_id"] if row else None
