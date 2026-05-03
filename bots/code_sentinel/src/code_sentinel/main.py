"""Code Sentinel 봇 엔트리포인트.

실행:
    uv run python -m code_sentinel.main

환경변수:
    DISCORD_BOT_TOKEN_CODE (필수)
    ANTHROPIC_API_KEY (필수)
    GITHUB_PAT (선택, private repo PR 처리 시 필수)
    DISCORD_GUILD_ID (선택)
    COST_MONTHLY_LIMIT_KRW_CODE (선택)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from sd_core.discord.base_bot import SecuDeckBot
from sd_core.utils.errors import ConfigError
from sd_core.utils.logger import get_logger

from code_sentinel.commands import install_commands
from code_sentinel.github_fetcher import GitHubFetcher
from code_sentinel.reviewer import CodeReviewer


load_dotenv()

_log = get_logger("code_sentinel.main")

_BOT_ROOT = Path(__file__).resolve().parents[2]
_RULES_DIR = _BOT_ROOT / "rules"
_PROMPTS_DIR = _BOT_ROOT / "prompts"


async def _async_main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN_CODE")
    if not token:
        raise ConfigError("DISCORD_BOT_TOKEN_CODE 환경변수가 비어 있습니다.")

    bot = SecuDeckBot(bot_name="code_sentinel")

    reviewer = CodeReviewer(
        llm=bot.llm,
        argos=bot.argos,
        rules_dir=_RULES_DIR,
        prompts_dir=_PROMPTS_DIR,
    )
    fetcher = GitHubFetcher()
    install_commands(bot, reviewer, fetcher)

    _log.info(
        "starting_code_sentinel",
        rules_loaded=len(reviewer.matcher.rules),
        guild_sync=bot._sync_guild_id,
    )
    async with bot:
        await bot.start(token)


def main() -> None:
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        _log.info("shutdown_keyboard_interrupt")


if __name__ == "__main__":
    main()
