"""Interview Companion 봇 엔트리포인트.

실행:
    uv run python -m interview_companion.main

환경변수:
    DISCORD_BOT_TOKEN_INTERVIEW (필수)
    ANTHROPIC_API_KEY (필수)
    GOOGLE_API_KEY (필수, Gemini 가이드 압축·누적분석)
    DATABASE_URL (선택, 없으면 in-memory 폴백)
    DISCORD_GUILD_ID (선택)
    COST_MONTHLY_LIMIT_KRW_INTERVIEW (선택, 기본 50000)
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

from interview_companion.commands import install_commands
from interview_companion.insight_extractor import InsightExtractor
from interview_companion.internal_handlers import InterviewInternalHandlers
from interview_companion.interview_logger import InterviewLogger
from interview_companion.interview_prep import InterviewPrep
from interview_companion.storage import InterviewStorage


load_dotenv()

_log = get_logger("interview_companion.main")

_BOT_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _BOT_ROOT / "data"
_PROMPTS_DIR = _BOT_ROOT / "prompts"
_MIGRATIONS_DIR = _BOT_ROOT / "migrations"


async def _async_main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN_INTERVIEW")
    if not token:
        raise ConfigError("DISCORD_BOT_TOKEN_INTERVIEW 환경변수가 비어 있습니다.")

    bot = SecuDeckBot(bot_name="interview_companion")

    # 저장소 + 마이그레이션 (Postgres 없으면 in-memory 폴백)
    storage = InterviewStorage()
    await storage.init(migration_path=_MIGRATIONS_DIR / "001_interviews.sql")

    # 가이드 생성기 (Sonnet)
    prep = InterviewPrep(
        llm=bot.llm,
        argos=bot.argos,
        hypotheses_path=_DATA_DIR / "argos_hypotheses.yaml",
        prompt_path=_PROMPTS_DIR / "prep_guide.md",
    )

    # 정리/저장 (Flash 압축 + Sonnet 분석). 가설 카탈로그는 prep 의 mtime-aware 로더 공유
    logger_engine = InterviewLogger(
        llm=bot.llm,
        storage=storage,
        log_prompt_path=_PROMPTS_DIR / "log_summary.md",
        get_hypotheses=prep.all_hypotheses,
    )

    # 누적 분석 (Gemini Flash, 1M 컨텍스트)
    insight_engine = InsightExtractor(
        llm=bot.llm,
        storage=storage,
        prompt_path=_PROMPTS_DIR / "pattern_analysis.md",
        get_hypotheses=prep.all_hypotheses,
    )

    install_commands(bot, prep, logger_engine, insight_engine, storage)

    # cos 위임용 내부 API.
    handlers = InterviewInternalHandlers(prep, insight_engine)
    api = InternalAPIServer(bot_name="interview_companion")
    api.register("interview_prep", handlers.interview_prep)
    api.register("interview_insight", handlers.interview_insight)

    _log.info(
        "starting_interview_companion",
        hypotheses=len(prep.all_hypotheses()),
        postgres_active=storage.pool is not None,
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
