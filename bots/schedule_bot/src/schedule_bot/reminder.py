"""30분 전 알림 백그라운드 태스크 — discord.py ``tasks.loop`` 기반 Cog.

설계 결정:
- 매 1분 polling — 30분 후 시작 일정을 ``date`` + ``time`` 정확 일치로 조회.
  cron 으로 30분 단위만 돌리는 방안도 있지만 분 단위 일정도 지원하려면 1분이 안전.
- 발송 권한 없는 채널은 조용히 스킵 + 로그 — 무한 재시도 방지.
- ``remind_sent=1`` 플래그로 중복 발송 차단 (봇 재시작·중복 인스턴스 대비).
- 봇 ``wait_until_ready`` 후 시작 — 부팅 직후 ``get_channel`` 이 None 반환하는 레이스 방지.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks

from sd_core.utils.logger import get_logger

from schedule_bot import database as db


_log = get_logger("schedule_bot.reminder")


class ReminderCog(commands.Cog):
    """30분 전 알림 코그."""

    def __init__(self, bot: discord.Client):
        self.bot = bot

    async def cog_load(self) -> None:
        # discord.py 2.x — Cog 가 봇에 추가될 때 자동 호출. 여기서 loop 시작.
        self.reminder_loop.start()

    async def cog_unload(self) -> None:
        self.reminder_loop.cancel()

    @tasks.loop(minutes=1)
    async def reminder_loop(self) -> None:
        """매 1분 — 30분 후 시작 일정 발송."""
        now = datetime.now()
        remind_at = now + timedelta(minutes=30)
        target_date = remind_at.strftime("%Y-%m-%d")
        target_time = remind_at.strftime("%H:%M")

        try:
            pending = db.get_pending_reminders(target_date, target_time)
        except Exception as exc:  # noqa: BLE001 — DB 오류로 loop 죽지 않게
            _log.warning("reminder_db_failed", error=str(exc))
            return

        for schedule in pending:
            await self._send_one(schedule)

    async def _send_one(self, schedule: dict) -> None:
        """단일 일정 알림 임베드 발송. 권한 부족은 조용히 스킵."""
        channel_id = schedule.get("reminder_channel_id")
        if not channel_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return

        embed = discord.Embed(
            title="🔔 일정 알림 — 30분 후 시작!",
            color=0xFEE75C,  # 노랑: 주의 환기
        )
        embed.add_field(name="📌 일정", value=schedule["title"], inline=False)
        embed.add_field(
            name="⏰ 시작 시간",
            value=f"{schedule['date']} {schedule['time']}",
            inline=True,
        )
        if schedule.get("description"):
            embed.add_field(name="📝 내용", value=schedule["description"], inline=False)
        embed.set_footer(text=f"등록자: {schedule['created_by']}")

        try:
            await channel.send(embed=embed)
            db.mark_reminder_sent(schedule["id"])
        except discord.Forbidden:
            # 채널 권한 없음 — 무한 재시도 방지 위해 마킹.
            _log.warning("reminder_channel_forbidden", channel_id=channel_id)
            db.mark_reminder_sent(schedule["id"])
        except Exception as exc:  # noqa: BLE001
            # 일시 오류는 마킹하지 않고 다음 cycle 에서 재시도.
            _log.warning(
                "reminder_send_failed",
                schedule_id=schedule.get("id"),
                error=str(exc),
            )

    @reminder_loop.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()


__all__ = ["ReminderCog"]
