"""cos 의 디스코드 진입점 — @cos 멘션 리스너 + /council placeholder.

설계:
- ``on_message`` 리스너 1개로 모든 자연어 진입을 처리. 길드 채팅·DM 어디서든 동작.
- 일반 명령은 슬래시 커맨드 대신 멘션 우선(라우팅 봇 특성). ``/council`` 만 명시적 커맨드.
- 봇끼리의 핑퐁(infinite loop) 방지 — ``message.author.bot`` 인 메시지는 무시.
- Discord 임베드 description 한도(4096) 보호는 ``ui.py`` 에서 처리. 여기선 길이 검사 안 함.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from sd_core.utils.errors import ConfigError, SecuDeckError
from sd_core.utils.logger import get_logger

from chief_of_staff.delegator import Delegator
from chief_of_staff.intent_router import IntentRouter, RouteInput
from chief_of_staff.synthesizer import Synthesizer
from chief_of_staff.ui import (
    make_council_placeholder_embed,
    make_delegated_embed,
    make_delegated_failed_embed,
    make_routing_failed_embed,
    make_self_embed,
)


_log = get_logger("chief_of_staff.commands")


# ---------------------------------------------------------------------
# 멘션 리스너 — Cog 형태로 묶어 봇에 등록.
# ---------------------------------------------------------------------
class CosMessageRouter(commands.Cog):
    """``@cos`` 멘션 → 의도 분류 → 위임 또는 self 답변."""

    def __init__(
        self,
        bot: commands.Bot,
        router: IntentRouter,
        delegator: Delegator,
        synthesizer: Synthesizer,
    ):
        self.bot = bot
        self.router = router
        self.delegator = delegator
        self.synthesizer = synthesizer

    # -----------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # 1. 봇 메시지·자기 자신·시스템 메시지는 무시.
        if message.author.bot:
            return
        if self.bot.user is None:
            return
        # 2. 멘션 대상에 cos 가 없으면 패스.
        if self.bot.user not in message.mentions:
            return
        # 3. @everyone / @here 대량 트리거 방어 — 명시 멘션만 처리.
        if message.mention_everyone:
            return

        user_id = str(message.author.id)
        _log.info(
            "cos_mention_received",
            user_id=user_id,
            channel_id=str(message.channel.id) if message.channel else None,
            content_len=len(message.content or ""),
            attachments=len(message.attachments),
        )

        # 4. "보고 있어요" 신호 — 디스코드 typing indicator. 위임 호출이 길어질 수 있으므로.
        async with message.channel.typing():
            await self._handle(message, user_id)

    # -----------------------------------------------------------------
    async def _handle(self, message: discord.Message, user_id: str) -> None:
        route_in = self._build_route_input(message)

        # 1) 의도 분류
        intent = await self.router.classify(route_in, user_id)
        _log.info(
            "cos_intent_classified",
            user_id=user_id,
            bot=intent.bot,
            action=intent.action,
            source=intent.source,
            confidence=intent.confidence,
        )

        # 2) self 면 직접 답변
        if intent.bot == "self":
            result = await self.synthesizer.answer_self(route_in.text, user_id)
            await self._reply(message, embed=make_self_embed(result.body, cost_krw=result.cost_krw))
            return

        # 3) 위임
        intro = self.synthesizer.make_delegation_intro(intent)
        try:
            delegated = await self.delegator.execute(intent, message, user_id)
        except ConfigError as exc:
            # cos 설정 오류 (BOT_URL_* 누락 등) — 사용자에게 안내.
            _log.warning("cos_delegate_config_error", bot=intent.bot, error=str(exc))
            await self._reply(
                message,
                embed=make_delegated_failed_embed(intent.bot, exc.user_message),
            )
            return
        except SecuDeckError as exc:
            # 페이로드 빌드 실패 등 위임 가능 입력이 부족한 경우.
            _log.info("cos_delegate_input_missing", bot=intent.bot, error=str(exc))
            await self._reply(
                message,
                embed=make_routing_failed_embed(exc.user_message),
            )
            return
        except Exception as exc:  # noqa: BLE001
            _log.exception("cos_delegate_unexpected", bot=intent.bot, error=str(exc))
            await self._reply(
                message,
                embed=make_delegated_failed_embed(intent.bot, "예상치 못한 오류가 발생했어요."),
            )
            return

        # 4) 위임 결과 표시 — ok=False 면 안내 임베드.
        if not delegated.get("ok", True):
            summary = str(delegated.get("summary") or "봇이 처리하지 못했어요.")
            await self._reply(
                message,
                embed=make_delegated_failed_embed(intent.bot, summary),
            )
            return

        embed = make_delegated_embed(
            bot=intent.bot,
            action=intent.action,
            intro=intro,
            body=str(delegated.get("summary") or ""),
            cost_krw=float(delegated.get("cost_krw") or 0.0),
            blocks=list(delegated.get("blocks") or []),
        )
        await self._reply(message, embed=embed)

    # -----------------------------------------------------------------
    @staticmethod
    def _build_route_input(message: discord.Message) -> RouteInput:
        """디스코드 객체 의존성을 IntentRouter 에서 떼어내는 어댑터."""
        names: list[str] = []
        ctypes: list[str] = []
        for att in message.attachments:
            names.append(att.filename or "")
            ctypes.append(att.content_type or "")
        return RouteInput(
            text=message.content or "",
            attachment_filenames=names,
            attachment_content_types=ctypes,
        )

    # -----------------------------------------------------------------
    @staticmethod
    async def _reply(message: discord.Message, *, embed: discord.Embed) -> None:
        """답글 전송. 첨부 권한·디스패처 오류는 로그만 남기고 무시."""
        try:
            await message.reply(embed=embed, mention_author=False)
        except discord.HTTPException as exc:
            _log.warning("cos_reply_failed", error=str(exc))


# ---------------------------------------------------------------------
# /council — Phase 5 placeholder.
# ---------------------------------------------------------------------
class CouncilCommand(app_commands.Group):
    """``/council`` 슬래시 커맨드 그룹.

    Phase 5 (Council 모드) 도입 전까지는 안내 임베드만 반환. 비용 폭발 위험으로
    멘션 자연어로는 절대 트리거되지 않게, 항상 명시적 슬래시 커맨드만 받는다.
    """

    def __init__(self) -> None:
        super().__init__(name="council", description="5봇 카운슬 모드 (Phase 5)")

    @app_commands.command(name="start", description="Council 모드 시작 (Phase 5 미구현)")
    @app_commands.describe(topic="회의 안건 (Phase 5 활성화 후 사용)")
    async def start(self, interaction: discord.Interaction, topic: str | None = None) -> None:
        # ``topic`` 인자는 Phase 5 시그니처 호환을 위해 미리 받아둠.
        _log.info(
            "council_placeholder_invoked",
            user_id=str(interaction.user.id),
            topic=(topic or "")[:80],
        )
        await interaction.response.send_message(
            embed=make_council_placeholder_embed(),
            ephemeral=True,
        )


# ---------------------------------------------------------------------
# 봇 등록 헬퍼 — main.py 가 호출.
# ---------------------------------------------------------------------
async def install_commands(
    bot: commands.Bot,
    *,
    router: IntentRouter,
    delegator: Delegator,
    synthesizer: Synthesizer,
) -> None:
    """cos Cog + /council 그룹을 봇에 등록."""
    await bot.add_cog(CosMessageRouter(bot, router, delegator, synthesizer))
    bot.tree.add_command(CouncilCommand())
