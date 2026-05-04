"""Design Echo 봇 엔트리포인트.

실행:
    uv run python -m design_echo.main

환경변수:
    DISCORD_BOT_TOKEN_DESIGN (필수)
    GOOGLE_API_KEY (필수, Vision)
    ANTHROPIC_API_KEY (필수, 톤·카피)
    DISCORD_GUILD_ID (선택)
    COST_MONTHLY_LIMIT_KRW_DESIGN (선택, 기본 50000)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from sd_core.discord.base_bot import SecuDeckBot
from sd_core.discord.internal_api import InternalAPIServer
from sd_core.utils.errors import ConfigError
from sd_core.utils.logger import get_logger

from design_echo.commands import install_commands
from design_echo.consistency_checker import ConsistencyChecker
from design_echo.copy_reviewer import CopyReviewer
from design_echo.design_system import DesignSystem
from design_echo.internal_handlers import DesignInternalHandlers
from design_echo.spec_generator import SpecGenerator


load_dotenv()

_log = get_logger("design_echo.main")

_BOT_ROOT = Path(__file__).resolve().parents[2]
_DS_DIR = _BOT_ROOT / "design_system"
_PROMPTS_DIR = _BOT_ROOT / "prompts"


async def _async_main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN_DESIGN")
    if not token:
        raise ConfigError("DISCORD_BOT_TOKEN_DESIGN 환경변수가 비어 있습니다.")

    bot = SecuDeckBot(bot_name="design_echo")

    ds = DesignSystem(_DS_DIR)
    # 부팅 시 1회 로드 검증 (실패하면 ConfigError 로 즉시 알림)
    _ = ds.tokens()
    _ = ds.components()
    _ = ds.tone()

    checker = ConsistencyChecker(
        llm=bot.llm,
        ds=ds,
        check_prompt_path=_PROMPTS_DIR / "consistency_check.md",
        base_prompt_path=_PROMPTS_DIR / "system_base.md",
    )
    spec = SpecGenerator(
        llm=bot.llm,
        ds=ds,
        spec_prompt_path=_PROMPTS_DIR / "handoff_spec.md",
        base_prompt_path=_PROMPTS_DIR / "system_base.md",
    )
    copy = CopyReviewer(
        llm=bot.llm,
        ds=ds,
        copy_prompt_path=_PROMPTS_DIR / "copy_review.md",
        base_prompt_path=_PROMPTS_DIR / "system_base.md",
    )

    install_commands(bot, checker, spec, copy)

    # cos 위임용 내부 API.
    handlers = DesignInternalHandlers(checker, spec, copy)
    api = InternalAPIServer(bot_name="design_echo")
    api.register("design_check", handlers.design_check)
    api.register("design_spec", handlers.design_spec)
    api.register("design_copy", handlers.design_copy)

    _log.info(
        "starting_design_echo",
        ds_components=len(ds.components()),
        ds_colors=len(ds.all_colors_flat()),
        guild_sync=bot._sync_guild_id,
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
