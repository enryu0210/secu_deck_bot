"""슬래시 커맨드 그룹 ``/일정`` — 등록·조회·수정·삭제·알림채널 9종.

LLM 호출 없음. 모든 동작은 SQLite + discord.py 로직만으로 수행.

설계 메모:
- ``app_commands.Group(name="일정", ...)`` 한 그룹에 9개 서브커맨드. 한국어 그룹·서브명 유지.
- 입력 검증(날짜·시간 포맷) 은 슬래시 단계에서 즉시 ephemeral 로 거절 — DB 까지 가지 않음.
- 알림 채널 설정만 ``manage_guild`` 권한 필요. 다른 명령은 누구나 가능 (팀 일정 공유 의도).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import discord
from discord import app_commands

from sd_core.utils.logger import get_logger

from schedule_bot import database as db
from schedule_bot.ui import (
    COLOR_ERROR,
    COLOR_SUCCESS,
    COLOR_WARNING,
    build_schedule_list_embed,
    format_schedule_embed,
)


_log = get_logger("schedule_bot.commands")

# 날짜·시간 포맷 상수 — 한국 사용자 기준 ISO 표준 형식.
DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


def _parse_date(date_str: str) -> datetime | None:
    """``YYYY-MM-DD`` 파싱. 잘못된 형식이면 None."""
    try:
        return datetime.strptime(date_str, DATE_FMT)
    except ValueError:
        return None


def _parse_time(time_str: str) -> str | None:
    """``HH:MM`` 검증. 유효하면 그대로 반환, 아니면 None."""
    try:
        datetime.strptime(time_str, TIME_FMT)
        return time_str
    except ValueError:
        return None


async def _send_error(interaction: discord.Interaction, message: str) -> None:
    """공통 에러 임베드 (ephemeral) — 사용자만 보이게."""
    await interaction.response.send_message(
        embed=discord.Embed(description=f"❌ {message}", color=COLOR_ERROR),
        ephemeral=True,
    )


class ScheduleCommands(app_commands.Group):
    """``/일정`` 슬래시 그룹."""

    def __init__(self):
        super().__init__(name="일정", description="📅 팀 일정을 관리합니다")

    # ─── /일정 등록 ───────────────────────────────────────────
    @app_commands.command(name="등록", description="새 일정을 등록합니다")
    @app_commands.describe(
        제목="일정 제목 (예: 팀 회의)",
        날짜="날짜 (형식: YYYY-MM-DD, 예: 2026-04-10)",
        시간="시간 (형식: HH:MM, 예: 14:30) — 선택사항",
        설명="일정 상세 설명 — 선택사항",
    )
    async def register(
        self,
        interaction: discord.Interaction,
        제목: str,
        날짜: str,
        시간: str | None = None,
        설명: str | None = None,
    ):
        parsed_date = _parse_date(날짜)
        if not parsed_date:
            await _send_error(interaction, "날짜 형식이 올바르지 않아요. `YYYY-MM-DD` 형식으로 입력해주세요. 예: `2026-04-10`")
            return

        parsed_time: str | None = None
        if 시간:
            parsed_time = _parse_time(시간)
            if not parsed_time:
                await _send_error(interaction, "시간 형식이 올바르지 않아요. `HH:MM` 형식으로 입력해주세요. 예: `14:30`")
                return

        created_by = str(interaction.user)
        new_id = db.add_schedule(
            guild_id=str(interaction.guild_id),
            title=제목,
            date=parsed_date.strftime(DATE_FMT),
            time=parsed_time,
            description=설명,
            created_by=created_by,
        )

        embed = discord.Embed(title="✅ 일정이 등록되었습니다!", color=COLOR_SUCCESS)
        embed.add_field(name="🆔 ID", value=str(new_id), inline=True)
        embed.add_field(name="📌 제목", value=제목, inline=True)
        embed.add_field(name="🗓️ 날짜", value=parsed_date.strftime(DATE_FMT), inline=True)
        embed.add_field(name="⏰ 시간", value=parsed_time if parsed_time else "시간 미정", inline=True)
        if 설명:
            embed.add_field(name="📝 설명", value=설명, inline=False)
        embed.set_footer(text=f"등록자: {created_by}")

        await interaction.response.send_message(embed=embed)

    # ─── /일정 목록 ───────────────────────────────────────────
    @app_commands.command(name="목록", description="앞으로 예정된 일정을 최대 10개 보여줍니다")
    async def list_upcoming(self, interaction: discord.Interaction):
        schedules = db.get_upcoming_schedules(str(interaction.guild_id), limit=10)
        embed = build_schedule_list_embed(schedules, "📋 예정된 일정 목록")
        await interaction.response.send_message(embed=embed)

    # ─── /일정 오늘 ───────────────────────────────────────────
    @app_commands.command(name="오늘", description="오늘의 일정을 보여줍니다")
    async def today(self, interaction: discord.Interaction):
        today_str = datetime.now().strftime(DATE_FMT)
        schedules = db.get_schedules_by_date(str(interaction.guild_id), today_str)
        embed = build_schedule_list_embed(schedules, f"📅 오늘({today_str}) 일정")
        await interaction.response.send_message(embed=embed)

    # ─── /일정 이번주 ─────────────────────────────────────────
    @app_commands.command(name="이번주", description="이번 주(오늘~일요일) 일정을 보여줍니다")
    async def this_week(self, interaction: discord.Interaction):
        today = datetime.now()
        # weekday: 월=0, 일=6 → 이번 주 일요일까지 며칠 남았는지
        days_until_sunday = 6 - today.weekday()
        sunday = today + timedelta(days=days_until_sunday)

        start_str = today.strftime(DATE_FMT)
        end_str = sunday.strftime(DATE_FMT)

        schedules = db.get_schedules_between(str(interaction.guild_id), start_str, end_str)
        embed = build_schedule_list_embed(schedules, f"📆 이번 주 일정 ({start_str} ~ {end_str})")
        await interaction.response.send_message(embed=embed)

    # ─── /일정 날짜검색 ───────────────────────────────────────
    @app_commands.command(name="날짜검색", description="특정 날짜의 일정을 조회합니다")
    @app_commands.describe(날짜="조회할 날짜 (형식: YYYY-MM-DD, 예: 2026-04-15)")
    async def search_by_date(self, interaction: discord.Interaction, 날짜: str):
        if not _parse_date(날짜):
            await _send_error(interaction, "날짜 형식이 올바르지 않아요. (`YYYY-MM-DD`)")
            return

        schedules = db.get_schedules_by_date(str(interaction.guild_id), 날짜)
        embed = build_schedule_list_embed(schedules, f"🔍 {날짜} 일정")
        await interaction.response.send_message(embed=embed)

    # ─── /일정 상세 ───────────────────────────────────────────
    @app_commands.command(name="상세", description="일정 ID로 상세 정보를 확인합니다")
    @app_commands.describe(id="조회할 일정의 ID 번호")
    async def detail(self, interaction: discord.Interaction, id: int):
        schedule = db.get_schedule_by_id(id, str(interaction.guild_id))
        if not schedule:
            await _send_error(interaction, f"ID `{id}`에 해당하는 일정을 찾을 수 없어요.")
            return

        embed = format_schedule_embed(schedule)
        # created_at 은 ISO 형식이라 'T' 포함 — 가독성 위해 첫 19자만 (YYYY-MM-DDTHH:MM:SS).
        embed.add_field(name="📌 등록일시", value=schedule["created_at"][:19], inline=False)
        await interaction.response.send_message(embed=embed)

    # ─── /일정 수정 ───────────────────────────────────────────
    @app_commands.command(name="수정", description="등록된 일정을 수정합니다 (수정할 항목만 입력)")
    @app_commands.describe(
        id="수정할 일정의 ID 번호",
        제목="새 제목 — 선택사항",
        날짜="새 날짜 (YYYY-MM-DD) — 선택사항",
        시간="새 시간 (HH:MM) — 선택사항",
        설명="새 설명 — 선택사항",
    )
    async def edit(
        self,
        interaction: discord.Interaction,
        id: int,
        제목: str | None = None,
        날짜: str | None = None,
        시간: str | None = None,
        설명: str | None = None,
    ):
        # 존재 확인 — guild_id 포함 비교라 다른 서버 일정은 보이지 않음.
        schedule = db.get_schedule_by_id(id, str(interaction.guild_id))
        if not schedule:
            await _send_error(interaction, f"ID `{id}`에 해당하는 일정을 찾을 수 없어요.")
            return

        updates: dict[str, str] = {}
        if 제목:
            updates["title"] = 제목
        if 날짜:
            if not _parse_date(날짜):
                await _send_error(interaction, "날짜 형식이 올바르지 않아요. (`YYYY-MM-DD`)")
                return
            updates["date"] = 날짜
        if 시간:
            parsed_t = _parse_time(시간)
            if not parsed_t:
                await _send_error(interaction, "시간 형식이 올바르지 않아요. (`HH:MM`)")
                return
            updates["time"] = parsed_t
        if 설명 is not None:
            updates["description"] = 설명

        if not updates:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="⚠️ 수정할 내용을 하나 이상 입력해주세요.",
                    color=COLOR_WARNING,
                ),
                ephemeral=True,
            )
            return

        db.update_schedule(id, str(interaction.guild_id), **updates)

        embed = discord.Embed(title=f"✏️ 일정 [{id}] 수정 완료", color=COLOR_SUCCESS)
        label_map = {"title": "제목", "date": "날짜", "time": "시간", "description": "설명"}
        for key, val in updates.items():
            embed.add_field(name=label_map.get(key, key), value=val, inline=True)
        embed.set_footer(text=f"수정자: {interaction.user}")

        await interaction.response.send_message(embed=embed)

    # ─── /일정 삭제 ───────────────────────────────────────────
    @app_commands.command(name="삭제", description="일정을 삭제합니다")
    @app_commands.describe(id="삭제할 일정의 ID 번호")
    async def delete(self, interaction: discord.Interaction, id: int):
        schedule = db.get_schedule_by_id(id, str(interaction.guild_id))
        if not schedule:
            await _send_error(interaction, f"ID `{id}`에 해당하는 일정을 찾을 수 없어요.")
            return

        db.delete_schedule(id, str(interaction.guild_id))

        embed = discord.Embed(
            title="🗑️ 일정 삭제 완료",
            description=f"**[{id}] {schedule['title']}** 일정이 삭제되었습니다.",
            color=COLOR_WARNING,
        )
        embed.set_footer(text=f"삭제자: {interaction.user}")
        await interaction.response.send_message(embed=embed)

    # ─── /일정 알림채널 ───────────────────────────────────────
    @app_commands.command(
        name="알림채널",
        description="일정 30분 전 알림을 받을 채널을 설정합니다 (관리자 전용)",
    )
    @app_commands.describe(채널="알림을 받을 텍스트 채널")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_reminder_channel(
        self,
        interaction: discord.Interaction,
        채널: discord.TextChannel,
    ):
        db.set_reminder_channel(str(interaction.guild_id), str(채널.id))

        embed = discord.Embed(
            title="🔔 알림 채널 설정 완료",
            description=f"{채널.mention} 채널에서 일정 30분 전 알림을 받습니다.",
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    @set_reminder_channel.error
    async def set_reminder_channel_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        # 권한 부족만 별도 안내. 다른 에러는 base_bot 의 on_app_command_error 로 위임.
        if isinstance(error, app_commands.MissingPermissions):
            await _send_error(interaction, "알림 채널 설정은 **서버 관리자**만 가능합니다.")
            return
        raise error


def install_commands(bot) -> None:
    """슬래시 그룹 등록 — main.py 에서 호출."""
    bot.tree.add_command(ScheduleCommands())


__all__ = ["ScheduleCommands", "install_commands"]
