"""슬래시 커맨드 그룹 ``/pitch``.

- /pitch review : 6 페르소나 정밀 리뷰 (약 2분)
- /pitch quick  : 1분 이내 빠른 진단
- /pitch focus  : 단일 페르소나 깊이 리뷰
"""
from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands

from sd_core.utils.errors import SecuDeckError
from sd_core.utils.logger import get_logger

from pitch_sharpener.document_parser import DocumentParser, DocumentParseError
from pitch_sharpener.review_engine import ReviewEngine
from pitch_sharpener.ui import (
    PersonaSelectView,
    make_focused_embed,
    make_full_review_embeds,
    make_parse_warning_embed,
    make_quick_embed,
)


_log = get_logger("pitch_sharpener.commands")


class PitchCommands(app_commands.Group):
    """``/pitch`` 슬래시 커맨드 그룹."""

    def __init__(self, engine: ReviewEngine, parser: DocumentParser):
        super().__init__(name="pitch", description="사업계획서 리뷰 봇")
        self.engine = engine
        self.parser = parser

    # -----------------------------------------------------------------
    @app_commands.command(name="review", description="6명 심사위원의 정밀 리뷰 (약 2분 소요)")
    @app_commands.describe(
        document="사업계획서 첨부 (PDF / DOCX / MD / TXT)",
        text="첨부 대신 본문 텍스트 직접 입력",
    )
    async def review(
        self,
        interaction: discord.Interaction,
        document: discord.Attachment | None = None,
        text: str | None = None,
    ):
        await interaction.response.defer(thinking=True)

        try:
            parsed = await self.parser.parse(document, text)
        except DocumentParseError as exc:
            await interaction.followup.send(
                embed=make_parse_warning_embed(str(exc)),
                ephemeral=True,
            )
            return

        result = await self.engine.full_review(
            document_text=parsed.raw_text,
            user_id=str(interaction.user.id),
        )

        embeds = make_full_review_embeds(result)
        # Discord 는 한 메시지에 최대 10개 임베드 — 7개라 안전
        await interaction.followup.send(embeds=embeds)

        if result.fallback_count > 0:
            _log.info(
                "full_review_with_fallback",
                fallbacks=result.fallback_count,
                total_cost_krw=result.total_cost_krw,
            )

    # -----------------------------------------------------------------
    @app_commands.command(name="quick", description="1분 이내 빠른 진단")
    @app_commands.describe(
        document="사업계획서 첨부",
        text="첨부 대신 본문 텍스트 직접 입력",
    )
    async def quick(
        self,
        interaction: discord.Interaction,
        document: discord.Attachment | None = None,
        text: str | None = None,
    ):
        await interaction.response.defer(thinking=True)

        try:
            parsed = await self.parser.parse(document, text)
        except DocumentParseError as exc:
            await interaction.followup.send(
                embed=make_parse_warning_embed(str(exc)),
                ephemeral=True,
            )
            return

        result = await self.engine.quick_diagnosis(
            document_text=parsed.raw_text,
            user_id=str(interaction.user.id),
        )
        await interaction.followup.send(embed=make_quick_embed(result.text, result.cost_krw))

    # -----------------------------------------------------------------
    @app_commands.command(name="focus", description="특정 영역만 깊이 리뷰")
    @app_commands.describe(
        document="사업계획서 첨부",
        text="첨부 대신 본문 텍스트 직접 입력",
    )
    async def focus(
        self,
        interaction: discord.Interaction,
        document: discord.Attachment | None = None,
        text: str | None = None,
    ):
        await interaction.response.defer(thinking=True, ephemeral=False)

        try:
            parsed = await self.parser.parse(document, text)
        except DocumentParseError as exc:
            await interaction.followup.send(
                embed=make_parse_warning_embed(str(exc)),
                ephemeral=True,
            )
            return

        # 페르소나 선택 Select 를 띄우고 콜백에서 리뷰 실행.
        async def _on_select(
            select_interaction: discord.Interaction,
            persona_id: str,
            doc_text: str,
        ) -> None:
            await select_interaction.response.defer(thinking=True)
            try:
                result = await self.engine.focused_review(
                    document_text=doc_text,
                    persona_id=persona_id,
                    user_id=str(select_interaction.user.id),
                )
            except SecuDeckError as exc:
                await select_interaction.followup.send(exc.user_message, ephemeral=True)
                return
            await select_interaction.followup.send(
                embed=make_focused_embed(result.persona_review)
            )

        view = PersonaSelectView(
            personas=self.engine.personas,
            document_text=parsed.raw_text,
            on_select=_on_select,
        )
        await interaction.followup.send(
            content="어떤 영역을 집중 리뷰할까요? 60초 안에 선택해 주세요.",
            view=view,
        )


def install_commands(bot, engine: ReviewEngine, parser: DocumentParser) -> None:
    """봇 트리에 ``/pitch`` 그룹을 등록."""
    bot.tree.add_command(PitchCommands(engine, parser))
