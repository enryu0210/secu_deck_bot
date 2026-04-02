"""
commands/schedule_commands.py
스케줄 관련 슬래시 커맨드를 정의하는 모듈.
각 커맨드는 discord.app_commands.command 데코레이터로 등록된다.
"""

import discord
from discord import app_commands
from datetime import datetime, timedelta
import database as db

# 날짜 포맷 상수
DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"

# 임베드 색상
COLOR_PRIMARY  = 0x5865F2  # 디스코드 블루
COLOR_SUCCESS  = 0x57F287  # 초록
COLOR_WARNING  = 0xFEE75C  # 노랑
COLOR_ERROR    = 0xED4245  # 빨강
COLOR_INFO     = 0xEB459E  # 분홍


def _parse_date(date_str: str) -> datetime | None:
    """
    'YYYY-MM-DD' 형식의 문자열을 datetime으로 파싱.
    잘못된 형식이면 None을 반환한다.
    """
    try:
        return datetime.strptime(date_str, DATE_FMT)
    except ValueError:
        return None


def _parse_time(time_str: str) -> str | None:
    """
    'HH:MM' 형식 검증. 유효하면 그대로 반환, 아니면 None.
    """
    try:
        datetime.strptime(time_str, TIME_FMT)
        return time_str
    except ValueError:
        return None


def _format_schedule_embed(schedule: dict, title_prefix: str = "") -> discord.Embed:
    """
    일정 dict를 받아 보기 좋은 Embed 객체로 변환한다.
    """
    title = f"{title_prefix}📅 [{schedule['id']}] {schedule['title']}"
    embed = discord.Embed(title=title, color=COLOR_PRIMARY)

    # 날짜·시간
    time_display = schedule["time"] if schedule["time"] else "시간 미정"
    embed.add_field(name="🗓️ 날짜", value=schedule["date"], inline=True)
    embed.add_field(name="⏰ 시간", value=time_display, inline=True)

    # 설명 (있을 때만)
    if schedule.get("description"):
        embed.add_field(name="📝 설명", value=schedule["description"], inline=False)

    embed.set_footer(text=f"등록자: {schedule['created_by']}")
    return embed


def _build_schedule_list_embed(schedules: list, title: str) -> discord.Embed:
    """
    여러 일정을 하나의 Embed에 목록으로 표시한다.
    일정이 없으면 안내 메시지를 보여준다.
    """
    embed = discord.Embed(title=title, color=COLOR_INFO)

    if not schedules:
        embed.description = "등록된 일정이 없어요. `/일정등록`으로 추가해보세요!"
        return embed

    for s in schedules:
        time_str = s["time"] if s["time"] else "시간 미정"
        value = f"⏰ {time_str}"
        if s.get("description"):
            # 설명이 길면 50자로 자름
            desc = s["description"][:50] + "..." if len(s["description"]) > 50 else s["description"]
            value += f"\n📝 {desc}"
        value += f"\n👤 {s['created_by']}"
        embed.add_field(
            name=f"[{s['id']}] {s['title']} — {s['date']}",
            value=value,
            inline=False
        )

    embed.set_footer(text=f"총 {len(schedules)}개 일정")
    return embed


class ScheduleCommands(app_commands.Group):
    """
    /일정 으로 시작하는 커맨드 그룹.
    예: /일정 등록, /일정 삭제 등
    """

    def __init__(self):
        super().__init__(name="일정", description="📅 팀 일정을 관리합니다")

    # ─── /일정 등록 ───────────────────────────────────────────
    @app_commands.command(name="등록", description="새 일정을 등록합니다")
    @app_commands.describe(
        제목="일정 제목 (예: 팀 회의)",
        날짜="날짜 (형식: YYYY-MM-DD, 예: 2026-04-10)",
        시간="시간 (형식: HH:MM, 예: 14:30) — 선택사항",
        설명="일정 상세 설명 — 선택사항"
    )
    async def register(self, interaction: discord.Interaction,
                       제목: str, 날짜: str,
                       시간: str = None, 설명: str = None):
        # 날짜 유효성 검사
        parsed_date = _parse_date(날짜)
        if not parsed_date:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ 날짜 형식이 올바르지 않아요.\n`YYYY-MM-DD` 형식으로 입력해주세요.\n예: `2026-04-10`",
                    color=COLOR_ERROR
                ), ephemeral=True
            )
            return

        # 시간 유효성 검사 (입력한 경우에만)
        parsed_time = None
        if 시간:
            parsed_time = _parse_time(시간)
            if not parsed_time:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="❌ 시간 형식이 올바르지 않아요.\n`HH:MM` 형식으로 입력해주세요.\n예: `14:30`",
                        color=COLOR_ERROR
                    ), ephemeral=True
                )
                return

        created_by = str(interaction.user)
        new_id = db.add_schedule(
            guild_id=str(interaction.guild_id),
            title=제목,
            date=parsed_date.strftime(DATE_FMT),
            time=parsed_time,
            description=설명,
            created_by=created_by
        )

        embed = discord.Embed(
            title="✅ 일정이 등록되었습니다!",
            color=COLOR_SUCCESS
        )
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
        embed = _build_schedule_list_embed(schedules, "📋 예정된 일정 목록")
        await interaction.response.send_message(embed=embed)

    # ─── /일정 오늘 ───────────────────────────────────────────
    @app_commands.command(name="오늘", description="오늘의 일정을 보여줍니다")
    async def today(self, interaction: discord.Interaction):
        today_str = datetime.now().strftime(DATE_FMT)
        schedules = db.get_schedules_by_date(str(interaction.guild_id), today_str)
        embed = _build_schedule_list_embed(schedules, f"📅 오늘({today_str}) 일정")
        await interaction.response.send_message(embed=embed)

    # ─── /일정 이번주 ─────────────────────────────────────────
    @app_commands.command(name="이번주", description="이번 주(오늘~일요일) 일정을 보여줍니다")
    async def this_week(self, interaction: discord.Interaction):
        today = datetime.now()
        # 이번 주 일요일까지 (weekday: 월=0, 일=6)
        days_until_sunday = 6 - today.weekday()
        sunday = today + timedelta(days=days_until_sunday)

        start_str = today.strftime(DATE_FMT)
        end_str = sunday.strftime(DATE_FMT)

        schedules = db.get_schedules_between(str(interaction.guild_id), start_str, end_str)
        embed = _build_schedule_list_embed(schedules, f"📆 이번 주 일정 ({start_str} ~ {end_str})")
        await interaction.response.send_message(embed=embed)

    # ─── /일정 날짜검색 ───────────────────────────────────────
    @app_commands.command(name="날짜검색", description="특정 날짜의 일정을 조회합니다")
    @app_commands.describe(날짜="조회할 날짜 (형식: YYYY-MM-DD, 예: 2026-04-15)")
    async def search_by_date(self, interaction: discord.Interaction, 날짜: str):
        parsed = _parse_date(날짜)
        if not parsed:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ 날짜 형식이 올바르지 않아요. (`YYYY-MM-DD`)",
                    color=COLOR_ERROR
                ), ephemeral=True
            )
            return

        schedules = db.get_schedules_by_date(str(interaction.guild_id), 날짜)
        embed = _build_schedule_list_embed(schedules, f"🔍 {날짜} 일정")
        await interaction.response.send_message(embed=embed)

    # ─── /일정 상세 ───────────────────────────────────────────
    @app_commands.command(name="상세", description="일정 ID로 상세 정보를 확인합니다")
    @app_commands.describe(id="조회할 일정의 ID 번호")
    async def detail(self, interaction: discord.Interaction, id: int):
        schedule = db.get_schedule_by_id(id, str(interaction.guild_id))
        if not schedule:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ ID `{id}`에 해당하는 일정을 찾을 수 없어요.",
                    color=COLOR_ERROR
                ), ephemeral=True
            )
            return

        embed = _format_schedule_embed(schedule)
        embed.add_field(name="📌 등록일시", value=schedule["created_at"][:19], inline=False)
        await interaction.response.send_message(embed=embed)

    # ─── /일정 수정 ───────────────────────────────────────────
    @app_commands.command(name="수정", description="등록된 일정을 수정합니다 (수정할 항목만 입력)")
    @app_commands.describe(
        id="수정할 일정의 ID 번호",
        제목="새 제목 — 선택사항",
        날짜="새 날짜 (YYYY-MM-DD) — 선택사항",
        시간="새 시간 (HH:MM) — 선택사항",
        설명="새 설명 — 선택사항"
    )
    async def edit(self, interaction: discord.Interaction, id: int,
                   제목: str = None, 날짜: str = None,
                   시간: str = None, 설명: str = None):
        # 일정 존재 여부 확인
        schedule = db.get_schedule_by_id(id, str(interaction.guild_id))
        if not schedule:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ ID `{id}`에 해당하는 일정을 찾을 수 없어요.",
                    color=COLOR_ERROR
                ), ephemeral=True
            )
            return

        # 수정할 항목 수집
        updates = {}
        if 제목:
            updates["title"] = 제목
        if 날짜:
            parsed = _parse_date(날짜)
            if not parsed:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="❌ 날짜 형식이 올바르지 않아요. (`YYYY-MM-DD`)",
                        color=COLOR_ERROR
                    ), ephemeral=True
                )
                return
            updates["date"] = 날짜
        if 시간:
            parsed_t = _parse_time(시간)
            if not parsed_t:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="❌ 시간 형식이 올바르지 않아요. (`HH:MM`)",
                        color=COLOR_ERROR
                    ), ephemeral=True
                )
                return
            updates["time"] = parsed_t
        if 설명 is not None:
            updates["description"] = 설명

        if not updates:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="⚠️ 수정할 내용을 하나 이상 입력해주세요.",
                    color=COLOR_WARNING
                ), ephemeral=True
            )
            return

        db.update_schedule(id, str(interaction.guild_id), **updates)

        embed = discord.Embed(
            title=f"✏️ 일정 [{id}] 수정 완료",
            color=COLOR_SUCCESS
        )
        for key, val in updates.items():
            label_map = {"title": "제목", "date": "날짜", "time": "시간", "description": "설명"}
            embed.add_field(name=label_map.get(key, key), value=val, inline=True)
        embed.set_footer(text=f"수정자: {interaction.user}")

        await interaction.response.send_message(embed=embed)

    # ─── /일정 삭제 ───────────────────────────────────────────
    @app_commands.command(name="삭제", description="일정을 삭제합니다")
    @app_commands.describe(id="삭제할 일정의 ID 번호")
    async def delete(self, interaction: discord.Interaction, id: int):
        schedule = db.get_schedule_by_id(id, str(interaction.guild_id))
        if not schedule:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ ID `{id}`에 해당하는 일정을 찾을 수 없어요.",
                    color=COLOR_ERROR
                ), ephemeral=True
            )
            return

        db.delete_schedule(id, str(interaction.guild_id))

        embed = discord.Embed(
            title="🗑️ 일정 삭제 완료",
            description=f"**[{id}] {schedule['title']}** 일정이 삭제되었습니다.",
            color=COLOR_WARNING
        )
        embed.set_footer(text=f"삭제자: {interaction.user}")
        await interaction.response.send_message(embed=embed)

    # ─── /일정 알림채널 ───────────────────────────────────────
    @app_commands.command(name="알림채널", description="일정 30분 전 알림을 받을 채널을 설정합니다 (관리자 전용)")
    @app_commands.describe(채널="알림을 받을 텍스트 채널")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_reminder_channel(self, interaction: discord.Interaction,
                                   채널: discord.TextChannel):
        db.set_reminder_channel(str(interaction.guild_id), str(채널.id))

        embed = discord.Embed(
            title="🔔 알림 채널 설정 완료",
            description=f"{채널.mention} 채널에서 일정 30분 전 알림을 받습니다.",
            color=COLOR_SUCCESS
        )
        await interaction.response.send_message(embed=embed)

    @set_reminder_channel.error
    async def set_reminder_channel_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ 알림 채널 설정은 **서버 관리자**만 가능합니다.",
                    color=COLOR_ERROR
                ), ephemeral=True
            )
