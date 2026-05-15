"""SecuDeckBot — 모든 Secu Deck 봇이 상속하는 베이스 클래스.

이 클래스는 다음을 한 곳에서 처리한다:
- discord.py Intents 표준 설정
- LLMRouter / ArgosContext / CostTracker 인스턴스 보관
- on_ready 시 슬래시 커맨드 동기화 (개발 중에는 길드 동기화)
- on_app_command_error 공통 에러 핸들러
"""
from __future__ import annotations

import os
from typing import Any

import discord
from discord.ext import commands

from sd_core.context.argos import ArgosContext
from sd_core.llm.router import LLMRouter
from sd_core.tracking.cost import CostTracker
from sd_core.tracking.usage import UsageTracker
from sd_core.utils.errors import (
    BudgetExceededError,
    ConfigError,
    LLMError,
    QuotaExceededError,
    SecuDeckError,
)
from sd_core.utils.logger import get_logger


class SecuDeckBot(commands.Bot):
    """공용 베이스. 봇별 main.py 에서 이걸 상속하지 않고 직접 인스턴스화 가능."""

    def __init__(
        self,
        bot_name: str,
        *,
        intents: discord.Intents | None = None,
        cost: CostTracker | None = None,
        usage: UsageTracker | None = None,
        argos_path: str | None = None,
        # 길드 ID 가 주어지면 개발 편의상 즉시 동기화 (글로벌 동기화는 최대 1시간)
        sync_guild_id: int | None = None,
    ):
        if intents is None:
            # 기본은 슬래시 커맨드 전용 봇 — Privileged Intent(message_content) 미요청.
            # 메시지 본문을 읽어야 하는 봇(cos 등)은 main.py 에서 ``intents`` 를
            # 직접 구성해 생성자에 주입해야 한다. 그러지 않으면 Discord 가
            # PrivilegedIntentsRequired 를 던지고 봇이 부팅하지 못한다.
            intents = discord.Intents.default()

        # command_prefix 는 슬래시 커맨드 위주이지만 명시적 설정 필요
        super().__init__(command_prefix="!", intents=intents, help_command=None)

        self.bot_name = bot_name
        self.cost = cost or CostTracker(bot_name)
        self.usage = usage or UsageTracker(bot_name)
        self.argos = ArgosContext(argos_path)
        self.llm = LLMRouter(cost=self.cost, usage=self.usage)
        self._log = get_logger("sd_core.bot", bot_name=bot_name)

        env_guild = sync_guild_id or os.getenv("DISCORD_GUILD_ID")
        try:
            self._sync_guild_id = int(env_guild) if env_guild else None
        except (TypeError, ValueError):
            self._sync_guild_id = None

    # -----------------------------------------------------------------
    # discord.py 라이프사이클 훅
    # -----------------------------------------------------------------
    async def setup_hook(self) -> None:
        """봇 객체 생성 직후 실행. 여기서 슬래시 커맨드 동기화."""
        if self._sync_guild_id:
            guild = discord.Object(id=self._sync_guild_id)
            # 글로벌 → 길드 복사 후 길드 동기화 (개발 중 즉시 반영)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            self._log.info("guild_sync_done", guild_id=self._sync_guild_id, count=len(synced))
        else:
            synced = await self.tree.sync()
            self._log.info("global_sync_done", count=len(synced))

    async def on_ready(self) -> None:
        self._log.info(
            "bot_ready",
            user=str(self.user),
            guilds=len(self.guilds),
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """모든 슬래시 커맨드의 공통 에러 처리.

        - 사용자에게는 user_message 만 노출.
        - 내부 디버그 메시지는 로그에만 기록.
        """
        # discord 가 감싸는 경우 원본 예외 추출
        original = getattr(error, "original", error)

        if isinstance(original, BudgetExceededError):
            user_msg = original.user_message
            log_level = "error"
        elif isinstance(original, QuotaExceededError):
            user_msg = original.user_message
            log_level = "warning"
        elif isinstance(original, LLMError):
            user_msg = original.user_message
            log_level = "warning"
        elif isinstance(original, ConfigError):
            user_msg = original.user_message
            log_level = "error"
        elif isinstance(original, SecuDeckError):
            user_msg = original.user_message
            log_level = "warning"
        else:
            user_msg = "예상치 못한 오류가 발생했어요. 잠시 후 다시 시도해 주세요."
            log_level = "error"

        getattr(self._log, log_level)(
            "app_command_error",
            command=getattr(interaction.command, "qualified_name", None),
            user_id=str(interaction.user.id) if interaction.user else None,
            error_type=type(original).__name__,
            error=str(original),
        )

        # 응답 전송 — 이미 응답된 인터랙션이면 followup 사용
        try:
            if interaction.response.is_done():
                await interaction.followup.send(user_msg, ephemeral=True)
            else:
                await interaction.response.send_message(user_msg, ephemeral=True)
        except discord.HTTPException as exc:
            self._log.warning("error_response_failed", error=str(exc))

    # -----------------------------------------------------------------
    # 편의 메서드
    # -----------------------------------------------------------------
    def env(self, key: str, default: Any = None) -> Any:
        """봇 코드에서 일관된 방식으로 환경변수 읽기."""
        return os.getenv(key, default)
