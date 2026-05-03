"""슬래시 커맨드 그룹 ``/design``.

- /design check : 시안 PNG/JPG 업로드 → DS 일관성 + 톤 체크
- /design spec  : 시안 → 개발 핸드오프 spec
- /design copy  : 카피 1개 → 톤 검토 + 3가지 대안
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from sd_core.utils.errors import SecuDeckError
from sd_core.utils.logger import get_logger

from design_echo.consistency_checker import ConsistencyChecker
from design_echo.copy_reviewer import CopyReviewer
from design_echo.spec_generator import SpecGenerator
from design_echo.ui import (
    make_check_embeds,
    make_copy_embed,
    make_input_error_embed,
    make_spec_embeds,
)


if TYPE_CHECKING:
    from sd_core.discord.base_bot import SecuDeckBot


_log = get_logger("design_echo.commands")

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB. Discord 첨부 제한 + Vision 토큰 보호


class DesignCommands(app_commands.Group):
    """``/design`` 슬래시 커맨드 그룹."""

    def __init__(
        self,
        checker: ConsistencyChecker,
        spec: SpecGenerator,
        copy: CopyReviewer,
    ):
        super().__init__(name="design", description="디자인 시스템·핸드오프·UX 라이팅")
        self.checker = checker
        self.spec_engine = spec
        self.copy_engine = copy

    # -----------------------------------------------------------------
    @app_commands.command(name="check", description="시안 일관성 + 톤 체크 (약 30초)")
    @app_commands.describe(image="디자인 시안 (PNG / JPG / WEBP, 8MB 이하)")
    async def check_cmd(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
    ):
        await interaction.response.defer(thinking=True)

        try:
            data = await _read_image(image)
        except ValueError as exc:
            await interaction.followup.send(
                embed=make_input_error_embed(str(exc)),
                ephemeral=True,
            )
            return

        try:
            result = await self.checker.check(data, user_id=str(interaction.user.id))
        except SecuDeckError as exc:
            await interaction.followup.send(exc.user_message, ephemeral=True)
            return

        await interaction.followup.send(embeds=make_check_embeds(result))

    # -----------------------------------------------------------------
    @app_commands.command(name="spec", description="개발 핸드오프 spec 생성 (약 60초)")
    @app_commands.describe(
        image="디자인 시안",
        screen_name="화면 이름 (예: 관리자 대시보드 / 점검 결과 페이지)",
    )
    async def spec_cmd(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        screen_name: str,
    ):
        await interaction.response.defer(thinking=True)

        try:
            data = await _read_image(image)
        except ValueError as exc:
            await interaction.followup.send(
                embed=make_input_error_embed(str(exc)),
                ephemeral=True,
            )
            return

        try:
            result = await self.spec_engine.generate(
                image_bytes=data,
                screen_name=screen_name,
                user_id=str(interaction.user.id),
            )
        except SecuDeckError as exc:
            await interaction.followup.send(exc.user_message, ephemeral=True)
            return

        await interaction.followup.send(
            embeds=make_spec_embeds(result.text, screen_name, result.cost_krw)
        )

    # -----------------------------------------------------------------
    @app_commands.command(name="copy", description="UX 라이팅 검토 + 3가지 대안")
    @app_commands.describe(
        screen_context="화면 컨텍스트 (예: 회원가입 완료 후)",
        purpose="카피 목적 (예: 다음 단계로 자연스럽게 이동)",
        current_copy="현재 카피 (한 문장 또는 한 단락)",
    )
    async def copy_cmd(
        self,
        interaction: discord.Interaction,
        screen_context: str,
        purpose: str,
        current_copy: str,
    ):
        await interaction.response.defer(thinking=True)
        try:
            result = await self.copy_engine.review(
                screen_context=screen_context,
                purpose=purpose,
                current_copy=current_copy,
                user_id=str(interaction.user.id),
            )
        except SecuDeckError as exc:
            await interaction.followup.send(exc.user_message, ephemeral=True)
            return
        await interaction.followup.send(embed=make_copy_embed(result.text, result.cost_krw))


# ---------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------
async def _read_image(attachment: discord.Attachment) -> bytes:
    """첨부 검증 + 다운로드. 형식·크기 위반 시 ValueError."""
    if attachment is None:
        raise ValueError("이미지를 첨부해 주세요.")
    name = attachment.filename or ""
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in _IMAGE_EXTS:
        raise ValueError(
            f"지원 안 하는 이미지 형식이에요: `{name}`\n"
            f"지원: {', '.join(sorted(_IMAGE_EXTS))} (PSD/Figma 는 PNG export 후 업로드)"
        )
    if attachment.size and attachment.size > _MAX_IMAGE_BYTES:
        raise ValueError(
            f"이미지가 너무 커요 ({attachment.size/1024/1024:.1f} MB). 8MB 이하로 줄여 주세요."
        )
    return await attachment.read()


def install_commands(
    bot: "SecuDeckBot",
    checker: ConsistencyChecker,
    spec: SpecGenerator,
    copy: CopyReviewer,
) -> None:
    bot.tree.add_command(DesignCommands(checker, spec, copy))
