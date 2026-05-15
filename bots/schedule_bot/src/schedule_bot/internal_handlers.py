"""Chief of Staff 위임용 액션 핸들러.

지원 액션 (조회 4 + 등록 1, 사용자 정책 결정):
- ``schedule_today``    : 오늘 일정. payload={guild_id}.
- ``schedule_week``     : 이번 주(오늘~일요일). payload={guild_id}.
- ``schedule_upcoming`` : 다가오는 일정 최대 10건. payload={guild_id, limit?}.
- ``schedule_search``   : 특정 날짜 일정. payload={guild_id, date(YYYY-MM-DD)}.
- ``schedule_register`` : 일정 등록. payload={guild_id, title, date(YYYY-MM-DD), time?(HH:MM),
                                              description?, created_by?}.

옵션 B (LLM 미호출) → ``cost_krw`` 는 항상 0.

설계:
- ``guild_id`` 는 cos delegator 가 디스코드 message 에서 자동 주입.
  핸들러가 누락 검출 시 ``SecuDeckError`` 로 친절 메시지 반환.
- 등록 시 ``created_by`` 가 비어 있으면 "cos 위임" 으로 마킹 — 출처 추적 용이.
- 모든 응답은 ``{ok, summary, blocks, cost_krw, error}`` 표준 형식.
  ``summary`` 는 cos 임베드 description 으로, ``blocks`` 는 임베드 field 후보.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sd_core.utils.errors import SecuDeckError
from sd_core.utils.logger import get_logger

from schedule_bot import database as db
from schedule_bot.ui import schedules_to_summary_text, summary_blocks_for_schedule


_log = get_logger("schedule_bot.internal_handlers")

DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


def _require_guild_id(payload: dict[str, Any]) -> str:
    """payload 에서 guild_id 추출. 누락 시 명확한 한국어 에러."""
    raw = payload.get("guild_id")
    if raw is None or str(raw).strip() == "":
        raise SecuDeckError(
            "guild_id 누락",
            user_message="일정 기능은 디스코드 서버 안에서만 사용할 수 있어요. (DM 에선 불가)",
        )
    return str(raw)


class ScheduleInternalHandlers:
    """cos 위임 5종 핸들러 — DB 모듈을 얇게 감쌌을 뿐."""

    # -----------------------------------------------------------------
    # 조회 — 오늘
    # -----------------------------------------------------------------
    async def schedule_today(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        guild_id = _require_guild_id(payload)
        today_str = datetime.now().strftime(DATE_FMT)
        rows = db.get_schedules_by_date(guild_id, today_str)
        summary = schedules_to_summary_text(rows, f"📅 **오늘({today_str}) 일정 — {len(rows)}건**")
        return {
            "ok": True,
            "summary": summary,
            "cost_krw": 0.0,
            "blocks": [
                {"title": "오늘 일정 수", "value": str(len(rows)), "inline": True},
                {"title": "기준 날짜", "value": today_str, "inline": True},
            ],
        }

    # -----------------------------------------------------------------
    # 조회 — 이번 주
    # -----------------------------------------------------------------
    async def schedule_week(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        guild_id = _require_guild_id(payload)
        today = datetime.now()
        # 월=0, 일=6 → 이번 주 일요일까지 며칠 남았는지
        days_until_sunday = 6 - today.weekday()
        sunday = today + timedelta(days=days_until_sunday)
        start_str = today.strftime(DATE_FMT)
        end_str = sunday.strftime(DATE_FMT)

        rows = db.get_schedules_between(guild_id, start_str, end_str)
        summary = schedules_to_summary_text(
            rows,
            f"📆 **이번 주 일정 ({start_str} ~ {end_str}) — {len(rows)}건**",
        )
        return {
            "ok": True,
            "summary": summary,
            "cost_krw": 0.0,
            "blocks": [
                {"title": "이번 주 일정 수", "value": str(len(rows)), "inline": True},
                {"title": "기간", "value": f"{start_str} ~ {end_str}", "inline": True},
            ],
        }

    # -----------------------------------------------------------------
    # 조회 — 다가오는 일정 (최대 10)
    # -----------------------------------------------------------------
    async def schedule_upcoming(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        guild_id = _require_guild_id(payload)
        try:
            limit = int(payload.get("limit") or 10)
        except (TypeError, ValueError):
            limit = 10

        rows = db.get_upcoming_schedules(guild_id, limit=limit)
        summary = schedules_to_summary_text(
            rows,
            f"📋 **다가오는 일정 — {len(rows)}건 (최대 {limit})**",
        )
        return {
            "ok": True,
            "summary": summary,
            "cost_krw": 0.0,
            "blocks": [
                {"title": "조회된 일정 수", "value": str(len(rows)), "inline": True},
                {"title": "limit", "value": str(limit), "inline": True},
            ],
        }

    # -----------------------------------------------------------------
    # 조회 — 특정 날짜
    # -----------------------------------------------------------------
    async def schedule_search(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        guild_id = _require_guild_id(payload)
        date_raw = (payload.get("date") or "").strip()
        if not date_raw:
            raise SecuDeckError(
                "date 누락",
                user_message="조회할 날짜를 알려주세요. 예: `2026-04-15`.",
            )
        # 포맷 검증 — DB 에 그대로 넣기 전에 거름.
        try:
            datetime.strptime(date_raw, DATE_FMT)
        except ValueError:
            raise SecuDeckError(
                f"잘못된 date 형식: {date_raw}",
                user_message="날짜는 `YYYY-MM-DD` 형식으로 알려주세요. 예: `2026-04-15`.",
            )

        rows = db.get_schedules_by_date(guild_id, date_raw)
        summary = schedules_to_summary_text(rows, f"🔍 **{date_raw} 일정 — {len(rows)}건**")
        return {
            "ok": True,
            "summary": summary,
            "cost_krw": 0.0,
            "blocks": [
                {"title": "조회 날짜", "value": date_raw, "inline": True},
                {"title": "건수", "value": str(len(rows)), "inline": True},
            ],
        }

    # -----------------------------------------------------------------
    # 등록
    # -----------------------------------------------------------------
    async def schedule_register(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        guild_id = _require_guild_id(payload)

        title = (payload.get("title") or "").strip()
        date_raw = (payload.get("date") or "").strip()
        time_raw = (payload.get("time") or "").strip() or None
        description = (payload.get("description") or "").strip() or None
        # cos 가 created_by 채워주면 사용자명, 아니면 위임 출처를 알 수 있게 마킹.
        created_by = (payload.get("created_by") or "").strip() or f"cos 위임 (user={user_id})"

        # 필수 필드 검증 — 두괄식 친절 안내.
        if not title:
            raise SecuDeckError(
                "title 누락",
                user_message="등록할 일정 제목을 알려주세요. 예: `팀 회의`.",
            )
        if not date_raw:
            raise SecuDeckError(
                "date 누락",
                user_message="일정 날짜가 필요해요. 예: `2026-04-15`.",
            )
        try:
            parsed_date = datetime.strptime(date_raw, DATE_FMT)
        except ValueError:
            raise SecuDeckError(
                f"잘못된 date 형식: {date_raw}",
                user_message="날짜는 `YYYY-MM-DD` 형식으로 알려주세요. 예: `2026-04-15`.",
            )

        if time_raw is not None:
            try:
                datetime.strptime(time_raw, TIME_FMT)
            except ValueError:
                raise SecuDeckError(
                    f"잘못된 time 형식: {time_raw}",
                    user_message="시간은 `HH:MM` 형식으로 알려주세요. 예: `14:30`.",
                )

        new_id = db.add_schedule(
            guild_id=guild_id,
            title=title,
            date=parsed_date.strftime(DATE_FMT),
            time=time_raw,
            description=description,
            created_by=created_by,
        )

        # 등록 결과를 cos 임베드용 dict 로 재구성 — DB 재조회 회피.
        registered = {
            "id": new_id,
            "title": title,
            "date": parsed_date.strftime(DATE_FMT),
            "time": time_raw,
            "description": description,
            "created_by": created_by,
        }

        summary_lines = [
            f"✅ **일정이 등록되었어요 — [{new_id}] {title}**",
            f"🗓️ {registered['date']}  ⏰ {time_raw or '시간 미정'}",
        ]
        if description:
            summary_lines.append(f"📝 {description}")
        summary_lines.append(f"👤 {created_by}")

        return {
            "ok": True,
            "summary": "\n".join(summary_lines),
            "cost_krw": 0.0,
            "blocks": summary_blocks_for_schedule(registered),
        }


__all__ = ["ScheduleInternalHandlers"]
