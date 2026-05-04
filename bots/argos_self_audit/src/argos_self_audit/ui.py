"""디스코드 임베드 빌더 — RenderedReport → discord.Embed.

색상 매핑은 ``sd_core.discord.ui`` 의 브랜드 컬러 팔레트와 일치.
"""
from __future__ import annotations

import discord

from sd_core.discord.ui import (
    make_error_embed,
    make_info_embed,
    make_success_embed,
    make_warning_embed,
    truncate_description,
)

from argos_self_audit.reporter import RenderedReport


def make_report_embed(report: RenderedReport) -> discord.Embed:
    """severity 에 따라 색상 다르게 매핑."""
    description = truncate_description(report.body, limit=4000)
    footer = report.footer or "Argos Self-Audit · 룰베이스 + 키워드 매핑"

    if report.severity == "CRIT":
        return make_error_embed(report.title, description, footer=footer)
    if report.severity == "WARN":
        return make_warning_embed(report.title, description, footer=footer)
    # INFO 는 아래 두 가지로 분기:
    # - body 에 "0건" 만 있는 깨끗한 결과는 success 로
    # - 그 외는 일반 info
    if "0건" in description and "🔴" not in description and "🟠" not in description:
        return make_success_embed(report.title, description, footer=footer)
    return make_info_embed(report.title, description, footer=footer)


def make_unavailable_embed(reason: str) -> discord.Embed:
    """기능 비활성/설정 누락 시 (예: ARGOS_REPO_URL 미설정)."""
    return make_warning_embed(
        title="⚙️ 기능 비활성",
        description=reason,
        footer="환경변수 설정 후 봇을 재시작해 주세요.",
    )


def mention_role_if_critical(severity: str, role_id: int | None) -> str:
    """CRITICAL 일 때만 ``<@&role_id>`` 멘션 문자열 생성. 일반 메시지에 prefix 로 붙임."""
    if severity == "CRIT" and role_id:
        return f"<@&{role_id}> "
    return ""


__all__ = [
    "make_report_embed",
    "make_unavailable_embed",
    "mention_role_if_critical",
]
