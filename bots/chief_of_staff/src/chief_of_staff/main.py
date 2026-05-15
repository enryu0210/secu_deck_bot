"""Chief of Staff 봇 엔트리포인트 (Phase 3 라우팅 모드).

실행:
    uv run python -m chief_of_staff.main

환경변수 (자세한 목록은 README.md 참조):
    DISCORD_BOT_TOKEN_COS         (필수)
    ANTHROPIC_API_KEY             (필수 — Haiku 의도 분류 + Sonnet self 답변)
    INTERNAL_API_SECRET           (필수 — 4봇과 공유)
    BOT_URL_PITCH / _CODE / _INTERVIEW / _DESIGN  (필수)
    BOT_URL_AUDIT                 (선택 — Stage 6 도입 후)
    BOT_URL_SCHEDULE              (선택 — 일정 봇 위임용)
    DISCORD_GUILD_ID              (선택 — 개발 중 길드 동기화)
    COST_MONTHLY_LIMIT_KRW_COS    (선택 — 기본 30000)

cos 는 외부 HTTP 서버를 띄우지 않는다. 디스코드 게이트웨이 1개만 연결.
"""
from __future__ import annotations

import asyncio
import os

import discord
from dotenv import load_dotenv

from sd_core.discord.base_bot import SecuDeckBot
from sd_core.discord.internal_client import InternalAPIClient
from sd_core.utils.errors import ConfigError
from sd_core.utils.logger import get_logger

from chief_of_staff.commands import install_commands
from chief_of_staff.delegator import Delegator
from chief_of_staff.intent_router import IntentRouter
from chief_of_staff.synthesizer import Synthesizer


# 로컬 개발용 — Railway 에서는 시스템 환경변수가 우선, .env 가 없어도 무해.
load_dotenv()

_log = get_logger("chief_of_staff.main")


async def _async_main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN_COS")
    if not token:
        raise ConfigError("DISCORD_BOT_TOKEN_COS 환경변수가 비어 있습니다.")

    # cos 는 ``message_content`` intent 가 필수 (멘션 본문 분석).
    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True

    bot = SecuDeckBot(bot_name="chief_of_staff", intents=intents)

    # 위임 클라이언트 — INTERNAL_API_SECRET / BOT_URL_* 환경변수에서 자동 로드.
    client = InternalAPIClient()
    if not client.bot_urls:
        # cos 의 본질이 위임이라 1개도 없으면 부팅 의미 없음. 명확히 경고.
        _log.warning(
            "no_bot_urls_configured",
            hint="BOT_URL_PITCH / _CODE / _INTERVIEW / _DESIGN 중 최소 하나는 설정해야 위임이 동작해요.",
        )

    router = IntentRouter(llm=bot.llm)
    delegator = Delegator(client)
    synthesizer = Synthesizer(llm=bot.llm, argos=bot.argos)

    # commands.py 의 install_commands 는 async (Cog 추가 때문) → bot 라이프사이클 안에서 호출.
    async with bot:
        await install_commands(
            bot,
            router=router,
            delegator=delegator,
            synthesizer=synthesizer,
        )
        _log.info(
            "starting_chief_of_staff",
            bots_known=sorted(client.bot_urls.keys()),
            guild_sync=bot._sync_guild_id,
        )
        try:
            await bot.start_with_backoff(token)
        finally:
            # httpx.AsyncClient 정리 — 누수 방지.
            await client.close()


def main() -> None:
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        _log.info("shutdown_keyboard_interrupt")


if __name__ == "__main__":
    main()
