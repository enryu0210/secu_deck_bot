"""Design Echo Discord 임베드.

체크 결과는 OK/Warn/Error 분리 → 사용자가 한눈에 액션 우선순위 파악.
"""
from __future__ import annotations

import discord

from sd_core.discord.ui import (
    make_error_embed,
    make_info_embed,
    make_success_embed,
    make_warning_embed,
    truncate_description,
    truncate_field,
)

from design_echo.consistency_checker import CheckResult


_DISCLAIMER = "ℹ️ 자동 추출은 시안 렌더링·압축에 영향을 받을 수 있어요. 모호하면 디자이너 확인."


def make_check_embeds(result: CheckResult) -> list[discord.Embed]:
    """`/design check` 결과 — 등급별 임베드 분리."""
    embeds: list[discord.Embed] = []

    summary = result.summary
    err = [d for d in summary.diffs if d.severity == "error"]
    warn = [d for d in summary.diffs if d.severity == "warn"]
    ok = [d for d in summary.diffs if d.severity == "ok"]

    # 헤더 — 한 줄 요약
    header_color = (
        make_error_embed if err else
        (make_warning_embed if warn else make_success_embed)
    )
    header = header_color(
        title="🎨 Design Check 결과",
        description=(
            f"❌ 위반 **{len(err)}** · ⚠️ 검토 **{len(warn)}** · ✅ 일치 **{len(ok)}**\n"
            f"화면 텍스트 톤 이슈 **{len(result.tone_issues)}**"
        ),
        footer=f"호출 비용 약 {result.cost_krw:.1f}원 · {_DISCLAIMER}",
    )
    embeds.append(header)

    if err:
        embeds.append(make_error_embed(
            title="❌ DS 위반",
            description=truncate_description(_format_diffs(err)),
        ))
    if warn:
        embeds.append(make_warning_embed(
            title="⚠️ 검토 권장",
            description=truncate_description(_format_diffs(warn)),
        ))
    if ok and not err:
        # OK 가 많으면 너무 길어지므로 위반/경고가 없을 때만 노출
        embeds.append(make_success_embed(
            title="✅ DS 일치 항목",
            description=truncate_description(_format_diffs(ok[:20])),
            footer=f"총 {len(ok)}건 중 상위 20개" if len(ok) > 20 else None,
        ))

    if result.tone_issues:
        lines = []
        for i, issue in enumerate(result.tone_issues[:8], 1):
            lines.append(
                f'**#{i}** "{truncate_field(issue.text, 200)}"\n'
                f"  → {truncate_field(issue.issue, 300)}\n"
                f"  💡 {truncate_field(issue.suggestion, 400)}"
            )
        embeds.append(make_info_embed(
            title="📝 화면 텍스트 톤 이슈",
            description=truncate_description("\n\n".join(lines)),
        ))

    if result.parse_warning:
        embeds.append(make_warning_embed(
            title="⚠️ 추출 일부 누락",
            description=result.parse_warning,
        ))

    return embeds[:10]


def _format_diffs(diffs) -> str:
    return "\n".join(f"• [{d.kind}] {d.message}" for d in diffs)


# ---------------------------------------------------------------------
# spec
# ---------------------------------------------------------------------
def make_spec_embeds(text: str, screen_name: str, cost_krw: float) -> list[discord.Embed]:
    """`/design spec` 결과 — 길면 description 분할."""
    embeds: list[discord.Embed] = []
    chunks = _chunk_text(text, 3800)
    for i, chunk in enumerate(chunks):
        title = f"📐 Handoff Spec — {screen_name}"
        if len(chunks) > 1:
            title += f" ({i+1}/{len(chunks)})"
        embeds.append(make_info_embed(
            title=title,
            description=chunk,
            footer=(
                f"호출 비용 약 {cost_krw:.1f}원 · {_DISCLAIMER}"
                if i == len(chunks) - 1
                else None
            ),
        ))
    return embeds[:10]


# ---------------------------------------------------------------------
# copy
# ---------------------------------------------------------------------
def make_copy_embed(text: str, cost_krw: float) -> discord.Embed:
    return make_info_embed(
        title="✏️ UX 라이팅 검토",
        description=truncate_description(text),
        footer=f"호출 비용 약 {cost_krw:.1f}원 · 추천은 참고용, 최종 결정은 디자이너",
    )


# ---------------------------------------------------------------------
# 입력 에러
# ---------------------------------------------------------------------
def make_input_error_embed(message: str) -> discord.Embed:
    return make_error_embed(title="⚠️ 입력 확인", description=message)


# ---------------------------------------------------------------------
# 분할 유틸
# ---------------------------------------------------------------------
def _chunk_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if size + len(line) > max_chars and buf:
            chunks.append("".join(buf))
            buf = []
            size = 0
        buf.append(line)
        size += len(line)
    if buf:
        chunks.append("".join(buf))
    return chunks
