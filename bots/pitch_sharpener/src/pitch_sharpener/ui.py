"""Pitch Sharpener Discord UI 헬퍼.

긴 리뷰는 임베드 description 한도(4096자)를 넘기 쉬우니 페르소나별 임베드로 분할.
"""
from __future__ import annotations

import discord

from sd_core.discord.ui import (
    make_info_embed,
    make_warning_embed,
    truncate_description,
    truncate_field,
)

from pitch_sharpener.persona_runner import PersonaReview
from pitch_sharpener.review_engine import FullReviewResult


_FOOTER = "⚠️ 시뮬레이션 평가입니다. 실제 심사 결과를 보장하지 않습니다."


def make_persona_embed(review: PersonaReview) -> discord.Embed:
    """단일 페르소나 리뷰를 임베드 1개로."""
    title = f"{review.persona_emoji} {review.persona_name}"
    embed = make_info_embed(
        title=title,
        description=truncate_description(review.content, limit=4000),
        footer=_FOOTER,
    )
    return embed


def make_synthesis_embed(synthesis_text: str, total_cost_krw: float) -> discord.Embed:
    """종합 결과 임베드."""
    embed = make_info_embed(
        title="🏁 종합 심사 결과",
        description=truncate_description(synthesis_text, limit=4000),
        footer=f"이번 호출 비용 ≈ {total_cost_krw:.0f}원 · {_FOOTER}",
    )
    return embed


def make_full_review_embeds(result: FullReviewResult) -> list[discord.Embed]:
    """풀 리뷰 결과를 임베드 리스트로. 첫 번째는 종합, 이후 6개 페르소나."""
    embeds: list[discord.Embed] = [
        make_synthesis_embed(result.synthesis_text, result.total_cost_krw),
    ]
    # Discord 는 한 메시지당 최대 10개 임베드 — 종합 1 + 페르소나 6 = 7개로 안전.
    embeds.extend(make_persona_embed(r) for r in result.persona_reviews)
    return embeds


def make_quick_embed(text: str, cost_krw: float) -> discord.Embed:
    return make_info_embed(
        title="⚡ 빠른 진단",
        description=truncate_description(text),
        footer=f"이번 호출 비용 ≈ {cost_krw:.0f}원 · {_FOOTER}",
    )


def make_focused_embed(review: PersonaReview) -> discord.Embed:
    embed = make_info_embed(
        title=f"🔎 {review.persona_emoji} {review.persona_name} 집중 리뷰",
        description=truncate_description(review.content),
        footer=f"이번 호출 비용 ≈ {review.cost_krw:.0f}원 · {_FOOTER}",
    )
    return embed


def make_parse_warning_embed(reason: str) -> discord.Embed:
    return make_warning_embed(
        title="문서 파싱 알림",
        description=truncate_field(reason, limit=2000),
    )


class PersonaSelectView(discord.ui.View):
    """/pitch focus 에서 페르소나 선택용 Select."""

    def __init__(
        self,
        personas: list,
        document_text: str,
        on_select,           # 비동기 콜백 (interaction, persona_id, document_text) → None
        timeout: float = 60.0,
    ):
        super().__init__(timeout=timeout)
        self._on_select = on_select
        self._document_text = document_text

        options = [
            discord.SelectOption(
                label=f"{p.emoji} {p.name}",
                description=truncate_field(p.title, limit=100),
                value=p.id,
            )
            for p in personas
        ]
        self.add_item(_PersonaSelect(options, self._handle))

    async def _handle(self, interaction: discord.Interaction, persona_id: str) -> None:
        await self._on_select(interaction, persona_id, self._document_text)


class _PersonaSelect(discord.ui.Select):
    def __init__(self, options: list[discord.SelectOption], handler):
        super().__init__(
            placeholder="집중 리뷰할 심사위원을 선택하세요",
            min_values=1,
            max_values=1,
            options=options,
        )
        self._handler = handler

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        await self._handler(interaction, self.values[0])
