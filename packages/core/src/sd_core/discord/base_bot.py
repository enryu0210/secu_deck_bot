"""SecuDeckBot — 모든 Secu Deck 봇이 상속하는 베이스 클래스.

이 클래스는 다음을 한 곳에서 처리한다:
- discord.py Intents 표준 설정
- LLMRouter / ArgosContext / CostTracker 인스턴스 보관
- on_ready 시 슬래시 커맨드 동기화 (개발 중에는 길드 동기화)
- on_app_command_error 공통 에러 핸들러
"""
from __future__ import annotations

import asyncio
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
    # 부팅 안전장치
    # -----------------------------------------------------------------
    async def start_with_backoff(
        self,
        token: str,
        *,
        rate_limit_sleep: float = 60.0,
    ) -> None:
        """``start()`` 의 안전 래퍼 — Railway/PaaS 환경의 ``crash-loop`` 방지용.

        부팅 단계(``GET /users/@me``)에서 Discord 429(global rate limit) 같은
        일시 장애를 만나면, 예외를 다시 던지기 전에 컨테이너 안에서
        ``rate_limit_sleep`` 만큼 잠든다.

        왜:
        - PaaS 가 컨테이너를 즉시 재시작하면 1초당 60+회씩 ``/users/@me`` 를
          두드리게 되고, 이 트래픽 자체가 Discord 의 rate limit 윈도우를
          더 길게 만든다. (실제 2026-05-15 schedule_bot crash 때 다른 봇들까지
          429 에 휘말렸음.)
        - 컨테이너 안에서 sleep 으로 지연을 흡수하면 재시작 빈도가
          1초당 → 1분당으로 떨어져 악순환이 끊긴다.
        - 정상 부팅 시에는 아무런 비용도 들지 않는다 (try 블록의 happy path).
        """
        try:
            await self.start(token)
        except discord.errors.HTTPException as exc:
            # 429 외 다른 HTTPException(401 토큰 오류 등)은 backoff 의미 없음
            if exc.status == 429:
                self._log.error(
                    "startup_rate_limited",
                    status=exc.status,
                    sleep_sec=rate_limit_sleep,
                    hint="컨테이너 안에서 sleep 으로 재시작 폭주를 묶고 종료한다",
                )
                await asyncio.sleep(rate_limit_sleep)
            raise

    # -----------------------------------------------------------------
    # 편의 메서드
    # -----------------------------------------------------------------
    def env(self, key: str, default: Any = None) -> Any:
        """봇 코드에서 일관된 방식으로 환경변수 읽기."""
        return os.getenv(key, default)
