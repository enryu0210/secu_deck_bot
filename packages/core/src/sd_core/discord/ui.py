"""Discord 임베드·메시지 UI 헬퍼.

봇별로 임베드 레이아웃이 비슷하므로 공통 헬퍼로 묶음.
"""
from __future__ import annotations

import discord


# Argos 브랜드 컬러 (디자인팀 tokens.yaml 의 primary 500)
_BRAND_PRIMARY = 0x2563EB
_BRAND_DANGER = 0xDC2626
_BRAND_SUCCESS = 0x059669
_BRAND_WARNING = 0xD97706


def make_info_embed(title: str, description: str = "", *, footer: str | None = None) -> discord.Embed:
    """일반 정보 임베드 (Argos 브랜드 컬러)."""
    embed = discord.Embed(title=title, description=description, color=_BRAND_PRIMARY)
    if footer:
        embed.set_footer(text=footer)
    return embed


def make_success_embed(title: str, description: str = "", *, footer: str | None = None) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=_BRAND_SUCCESS)
    if footer:
        embed.set_footer(text=footer)
    return embed


def make_error_embed(title: str, description: str = "", *, footer: str | None = None) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=_BRAND_DANGER)
    if footer:
        embed.set_footer(text=footer)
    return embed


def make_warning_embed(title: str, description: str = "", *, footer: str | None = None) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=_BRAND_WARNING)
    if footer:
        embed.set_footer(text=footer)
    return embed


def truncate_field(text: str, limit: int = 1024) -> str:
    """Discord 임베드 필드 길이 제한 대응. 자르고 말줄임 표시."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def truncate_description(text: str, limit: int = 4096) -> str:
    """임베드 description 한도(4096자) 대응."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
