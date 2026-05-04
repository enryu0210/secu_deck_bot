"""디스코드 임베드 빌더 — cos 라우팅 응답 포맷.

원칙:
- 임베드 description 4096자 제한. 위임 봇 응답이 길면 분할이 아니라 절단(...).
- Council 모드는 Phase 5. 이 파일에는 placeholder 임베드만.
- 색상 구분: 위임=파랑, self=초록, 에러/안내=노랑.
"""
from __future__ import annotations

import discord


# 봇 식별자 → (이모지, 표시명).
BOT_DISPLAY: dict[str, tuple[str, str]] = {
    "pitch_sharpener": ("🎤", "Pitch Sharpener"),
    "code_sentinel": ("💻", "Code Sentinel"),
    "interview_companion": ("🎙", "Interview Companion"),
    "design_echo": ("🎨", "Design Echo"),
    "argos_self_audit": ("🛡", "Argos Self-Audit"),
    "self": ("🏛", "Chief of Staff"),
}


_DESC_LIMIT = 3900   # 4096 한계 안전 마진 (cos 문구 + 봇 응답 합산 대비)
_FIELD_LIMIT = 1024


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 4] + " …"


def _bot_label(bot: str) -> str:
    emoji, name = BOT_DISPLAY.get(bot, ("🤖", bot))
    return f"{emoji} {name}"


# ---------------------------------------------------------------------
# 위임 응답 임베드
# ---------------------------------------------------------------------
def make_delegated_embed(
    bot: str,
    action: str,
    intro: str,
    body: str,
    *,
    cost_krw: float = 0.0,
    blocks: list[dict] | None = None,
) -> discord.Embed:
    """위임 호출 결과 임베드.

    intro: cos 가 작성한 1~2문장 인트로.
    body: 위임 봇이 돌려준 summary 본문.
    """
    label = _bot_label(bot)
    description = f"{intro}\n\n---\n{body}".strip()
    embed = discord.Embed(
        title=f"{label} 가 답해드릴게요",
        description=_truncate(description, _DESC_LIMIT),
        color=0x4F8EE5,  # 파랑
    )
    embed.set_footer(text=f"action={action} · cost ≈ {cost_krw:.2f}원 · cos 라우팅")
    for b in (blocks or [])[:25]:
        embed.add_field(
            name=_truncate(str(b.get("title") or "-"), 256),
            value=_truncate(str(b.get("value") or "-"), _FIELD_LIMIT),
            inline=bool(b.get("inline", False)),
        )
    return embed


def make_self_embed(text: str, *, cost_krw: float = 0.0) -> discord.Embed:
    """cos 가 직접 답한 경우 (self 의도)."""
    embed = discord.Embed(
        title="🏛 Chief of Staff 가 직접 답해요",
        description=_truncate(text or "(빈 응답)", _DESC_LIMIT),
        color=0x4FB66B,  # 초록
    )
    embed.set_footer(text=f"cost ≈ {cost_krw:.2f}원 · cos self 답변")
    return embed


def make_routing_failed_embed(reason: str) -> discord.Embed:
    """의도 분류 자체가 실패해 cos 가 사용자에게 추가 정보를 요청할 때."""
    embed = discord.Embed(
        title="🤔 의도를 명확히 잡지 못했어요",
        description=_truncate(reason, _DESC_LIMIT),
        color=0xE5B454,  # 노랑
    )
    embed.set_footer(text="cos 라우팅 — 더 구체적인 요청을 보내주시면 도와드릴게요.")
    return embed


def make_delegated_failed_embed(bot: str, reason: str) -> discord.Embed:
    """위임 호출 자체가 실패한 경우."""
    label = _bot_label(bot)
    embed = discord.Embed(
        title=f"⚠️ {label} 호출 실패",
        description=_truncate(reason, _DESC_LIMIT),
        color=0xE57373,  # 빨강
    )
    embed.set_footer(text="잠시 후 다시 시도해 주세요.")
    return embed


# ---------------------------------------------------------------------
# /council placeholder (Phase 5)
# ---------------------------------------------------------------------
def make_council_placeholder_embed() -> discord.Embed:
    """Council 모드는 Phase 5 에서 활성화."""
    embed = discord.Embed(
        title="🏛 Council 모드는 아직 활성화되지 않았어요",
        description=(
            "Phase 5 에서 5봇 자율 협업 카운슬을 도입할 예정이에요.\n"
            "지금은 `@cos` 멘션으로 단일 봇 위임 라우팅만 지원합니다."
        ),
        color=0x9B6BD8,  # 보라
    )
    embed.set_footer(text="Phase 5 — 출시 안정기 진입 후 도입 예정")
    return embed


__all__ = [
    "make_delegated_embed",
    "make_self_embed",
    "make_routing_failed_embed",
    "make_delegated_failed_embed",
    "make_council_placeholder_embed",
    "BOT_DISPLAY",
]
