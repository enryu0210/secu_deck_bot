"""Schedule Bot 엔트리포인트.

실행:
    uv run python -m schedule_bot.main

환경변수 (README.md 참조):
    DISCORD_BOT_TOKEN_SCHEDULE       (필수)
    INTERNAL_API_SECRET              (필수 — cos 위임 인증)
    SCHEDULE_DB_PATH                 (선택 — SQLite 파일 경로. Railway Volume 권장)
    DISCORD_GUILD_ID                 (선택 — 슬래시 즉시 동기화)
    COST_MONTHLY_LIMIT_KRW_SCHEDULE  (선택 — LLM 미호출이라 사실상 0)
"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

from sd_core.discord.base_bot import SecuDeckBot
from sd_core.discord.internal_api import InternalAPIServer
from sd_core.utils.errors import ConfigError
from sd_core.utils.logger import get_logger

from schedule_bot import database as db
from schedule_bot.commands import install_commands
from schedule_bot.internal_handlers import ScheduleInternalHandlers
from schedule_bot.reminder import ReminderCog


load_dotenv()

_log = get_logger("schedule_bot.main")


async def _async_main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN_SCHEDULE")
    if not token:
        raise ConfigError("DISCORD_BOT_TOKEN_SCHEDULE 환경변수가 비어 있습니다.")

    # SQLite 테이블 초기화 — 부팅 1회. DB 파일 자동 생성.
    db.init_db()

    bot = SecuDeckBot(bot_name="schedule_bot")

    # 슬래시 그룹 등록 (sync) + 30분 전 알림 Cog (async — add_cog 는 awaitable).
    install_commands(bot)
    await bot.add_cog(ReminderCog(bot))

    # cos 위임용 internal API — fastapi + uvicorn 백그라운드 task.
    handlers = ScheduleInternalHandlers()
    api = InternalAPIServer(bot_name="schedule_bot")
    api.register("schedule_today", handlers.schedule_today)
    api.register("schedule_week", handlers.schedule_week)
    api.register("schedule_upcoming", handlers.schedule_upcoming)
    api.register("schedule_search", handlers.schedule_search)
    api.register("schedule_register", handlers.schedule_register)

    _log.info(
        "starting_schedule_bot",
        guild_sync=bot._sync_guild_id,
        db_path=os.getenv("SCHEDULE_DB_PATH") or "(default — bot dir)",
    )

    async with bot:
        await api.start()
        try:
            await bot.start(token)
        finally:
            await api.stop()


def main() -> None:
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        _log.info("shutdown_keyboard_interrupt")


if __name__ == "__main__":
    main()
