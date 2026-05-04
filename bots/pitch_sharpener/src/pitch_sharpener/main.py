"""Pitch Sharpener 봇 엔트리포인트.

실행:
    uv run python -m pitch_sharpener.main

환경변수:
    DISCORD_BOT_TOKEN_PITCH (필수)
    DISCORD_GUILD_ID (선택, 개발 중 길드 동기화)
    ANTHROPIC_API_KEY (필수)
    COST_MONTHLY_LIMIT_KRW_PITCH (선택, 기본 25000)
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

from pitch_sharpener.commands import install_commands
from pitch_sharpener.document_parser import DocumentParser
from pitch_sharpener.internal_handlers import PitchInternalHandlers
from pitch_sharpener.review_engine import ReviewEngine


# 로컬 개발용 — Railway 에서는 무시됨 (시스템 환경변수가 우선)
load_dotenv()

_log = get_logger("pitch_sharpener.main")

# 봇 패키지 루트(bots/pitch_sharpener) 기준 경로
_BOT_ROOT = Path(__file__).resolve().parents[2]
_PERSONAS_DIR = _BOT_ROOT / "personas"
_PROMPTS_DIR = _BOT_ROOT / "prompts"


async def _async_main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN_PITCH")
    if not token:
        raise ConfigError("DISCORD_BOT_TOKEN_PITCH 환경변수가 비어 있습니다.")

    bot = SecuDeckBot(bot_name="pitch_sharpener")

    # 엔진은 봇 객체와 동일 LLMRouter 를 공유 (비용 추적 일관)
    engine = ReviewEngine(
        llm=bot.llm,
        argos=bot.argos,
        personas_dir=_PERSONAS_DIR,
        prompts_dir=_PROMPTS_DIR,
    )
    parser = DocumentParser()
    install_commands(bot, engine, parser)

    # cos(Chief of Staff) 위임 호출용 내부 API. INTERNAL_API_SECRET 비어 있으면
    # 서버는 뜨지만 모든 호출이 503 으로 거부됨 → 우연한 노출 방지.
    handlers = PitchInternalHandlers(engine)
    api = InternalAPIServer(bot_name="pitch_sharpener")
    api.register("pitch_quick", handlers.pitch_quick)
    api.register("pitch_focus", handlers.pitch_focus)

    _log.info(
        "starting_pitch_sharpener",
        personas_loaded=len(engine.personas),
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
