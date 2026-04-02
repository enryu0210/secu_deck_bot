"""
bot.py
SecuDeck 스케줄 봇의 진입점.
슬래시 커맨드 등록, 30분 전 알림 태스크, 봇 실행을 담당한다.
"""

import os
import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timedelta
from dotenv import load_dotenv

import database as db
from commands.schedule_commands import ScheduleCommands

load_dotenv()

# ───────────────── 봇 초기화 ─────────────────

intents = discord.Intents.default()
intents.guilds = True


class ScheduleBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        # CommandTree: 슬래시 커맨드를 디스코드 서버에 등록하는 핵심 객체
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        """
        봇이 준비되기 전, 내부적으로 한 번 실행되는 설정 훅.
        커맨드 그룹을 트리에 추가하고 디스코드에 동기화한다.
        """
        self.tree.add_command(ScheduleCommands())

        # 전역 동기화: 최대 1시간 지연될 수 있음.
        # 개발 시 특정 길드에만 동기화하면 즉시 반영 가능.
        await self.tree.sync()
        print("✅ 슬래시 커맨드 동기화 완료")


bot = ScheduleBot()


# ───────────────── 이벤트 핸들러 ─────────────────

@bot.event
async def on_ready():
    db.init_db()  # DB 테이블 초기화 (없으면 생성)
    reminder_task.start()  # 30분 전 알림 백그라운드 태스크 시작
    print(f"✅ {bot.user} 온라인! 스케줄 봇 준비 완료.")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="/일정 등록 | 팀 일정 관리"
        )
    )


# ───────────────── 30분 전 알림 태스크 ─────────────────

@tasks.loop(minutes=1)
async def reminder_task():
    """
    매 1분마다 실행. 30분 후 시작되는 일정을 찾아 알림 채널에 메시지를 보낸다.
    왜 30분? 팀원들이 준비할 최소한의 시간을 주기 위함.
    """
    now = datetime.now()
    remind_at = now + timedelta(minutes=30)

    target_date = remind_at.strftime("%Y-%m-%d")
    target_time = remind_at.strftime("%H:%M")

    pending = db.get_pending_reminders(target_date, target_time)

    for schedule in pending:
        channel_id = schedule.get("reminder_channel_id")
        if not channel_id:
            continue

        channel = bot.get_channel(int(channel_id))
        if not channel:
            continue

        embed = discord.Embed(
            title="🔔 일정 알림 — 30분 후 시작!",
            color=0xFEE75C  # 노랑: 주의 환기
        )
        embed.add_field(name="📌 일정", value=schedule["title"], inline=False)
        embed.add_field(name="⏰ 시작 시간", value=f"{schedule['date']} {schedule['time']}", inline=True)
        if schedule.get("description"):
            embed.add_field(name="📝 내용", value=schedule["description"], inline=False)
        embed.set_footer(text=f"등록자: {schedule['created_by']}")

        try:
            await channel.send(embed=embed)
            db.mark_reminder_sent(schedule["id"])
        except discord.Forbidden:
            # 채널 권한 없음 — 조용히 무시 (무한 재시도 방지)
            print(f"⚠️ 알림 전송 권한 없음: 채널 {channel_id}")


@reminder_task.before_loop
async def before_reminder():
    """태스크 시작 전 봇이 완전히 준비될 때까지 대기."""
    await bot.wait_until_ready()


# ───────────────── 봇 실행 ─────────────────

bot.run(os.getenv("DISCORD_TOKEN"))
