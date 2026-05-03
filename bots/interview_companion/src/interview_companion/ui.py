"""Discord 임베드 헬퍼 — Interview Companion 전용.

핵심 원칙:
- 임베드 description 4096자 제한 / 필드 1024자 제한 준수
- 봇 응답 끝에 항상 비용·자동 분석 면책 한 줄
"""
from __future__ import annotations

from typing import Any

import discord

from sd_core.discord.ui import (
    make_error_embed,
    make_info_embed,
    make_success_embed,
    make_warning_embed,
    truncate_description,
    truncate_field,
)


_DISCLAIMER = (
    "ℹ️ 이 분석은 자동 추출 결과예요. 사업계획서에 인용 전 실제 발언을 확인해 주세요."
)


# ---------------------------------------------------------------------
# 가이드
# ---------------------------------------------------------------------
def make_guide_embed(text: str, focused: list[str], cost_krw: float) -> discord.Embed:
    """`/interview prep` 결과 임베드. text 가 길면 자른다."""
    embed = make_info_embed(
        title="📋 인터뷰 가이드 준비 완료",
        description=truncate_description(text),
        footer=f"집중 가설: {', '.join(focused) if focused else '자동 선택'} · 호출 비용 약 {cost_krw:.1f}원",
    )
    return embed


# ---------------------------------------------------------------------
# 로그
# ---------------------------------------------------------------------
def make_log_embeds(
    interview_number: int,
    target_display: str,
    summary: dict[str, Any],
    hypotheses_results: dict[str, Any],
    quotes: list[dict[str, Any]],
    cost_krw: float,
    parse_warning: str | None,
) -> list[discord.Embed]:
    """`/interview log` 결과 — 정보가 많아 임베드 2~3개로 분할."""
    embeds: list[discord.Embed] = []

    # 1) 메인 — 요약
    short = summary.get("short") or "요약을 생성하지 못했어요."
    key_points = summary.get("key_points") or []
    tone = summary.get("tone") or "-"

    desc_lines = [f"**한 줄 요약**\n{short}"]
    if key_points:
        desc_lines.append("\n**핵심 포인트**")
        for kp in key_points[:8]:
            desc_lines.append(f"• {kp}")
    desc_lines.append(f"\n**인터뷰이 톤**: {tone}")

    main = make_success_embed(
        title=f"📒 Interview Log #{interview_number:03d} — {target_display}",
        description=truncate_description("\n".join(desc_lines)),
        footer=f"호출 비용 약 {cost_krw:.1f}원 · {_DISCLAIMER}",
    )
    embeds.append(main)

    # 2) 가설 검증 결과
    if hypotheses_results:
        hyp_lines = []
        for hyp_id, body in hypotheses_results.items():
            if not isinstance(body, dict):
                continue
            verdict = body.get("verdict", "?")
            evidence = body.get("evidence", "")
            confidence = body.get("confidence", "")
            mark = _verdict_mark(verdict)
            hyp_lines.append(
                f"{mark} **{hyp_id}** [{confidence}]\n> {truncate_field(evidence, 600)}"
            )
        if hyp_lines:
            embeds.append(make_info_embed(
                title="🧪 가설 검증 결과",
                description=truncate_description("\n\n".join(hyp_lines)),
            ))

    # 3) 인용
    if quotes:
        q_lines = []
        for i, q in enumerate(quotes[:8], 1):
            text = q.get("text", "")
            hyp_id = q.get("hypothesis_id") or "-"
            sens = q.get("sensitivity", "?")
            q_lines.append(f'**#{i}** ({hyp_id} / 민감도 {sens})\n> "{truncate_field(text, 600)}"')
        embeds.append(make_info_embed(
            title="💬 인용 가능 발언",
            description=truncate_description("\n\n".join(q_lines)),
            footer="민감도 high 발언은 사업계획서 인용 시 익명화 권장",
        ))

    # 4) 파싱 경고가 있을 때만
    if parse_warning:
        embeds.append(make_warning_embed(
            title="⚠️ 정리 결과 일부 누락",
            description=parse_warning,
            footer="원문 메모는 그대로 보관되었어요.",
        ))

    return embeds


def _verdict_mark(verdict: str) -> str:
    v = (verdict or "").lower()
    if v == "verified":
        return "✅"
    if v == "refuted":
        return "❌"
    return "❓"


# ---------------------------------------------------------------------
# 인사이트
# ---------------------------------------------------------------------
def make_insight_embeds(text: str, count: int, cost_krw: float) -> list[discord.Embed]:
    """`/interview insight` 결과 — 길면 description 분할."""
    embeds: list[discord.Embed] = []
    chunks = _chunk_text(text, 3800)
    for i, chunk in enumerate(chunks):
        embed = make_info_embed(
            title=f"📊 누적 인터뷰 분석 — {count}건 종합" + (f" ({i+1}/{len(chunks)})" if len(chunks) > 1 else ""),
            description=chunk,
            footer=f"호출 비용 약 {cost_krw:.1f}원 · {_DISCLAIMER}" if i == len(chunks) - 1 else None,
        )
        embeds.append(embed)
    return embeds[:10]  # Discord 최대 10개


# ---------------------------------------------------------------------
# 인용 검색
# ---------------------------------------------------------------------
def make_quotes_embed(
    quotes: list[dict[str, Any]],
    keyword: str | None,
    hypothesis_id: str | None,
) -> discord.Embed:
    if not quotes:
        return make_warning_embed(
            title="🔍 검색 결과 없음",
            description=(
                f"키워드 `{keyword or '-'}` / 가설 `{hypothesis_id or '-'}` 에 해당하는 인용이 없어요.\n"
                "`/interview log` 로 더 많은 기록을 쌓은 뒤 다시 시도해 주세요."
            ),
        )

    lines = []
    for i, q in enumerate(quotes[:15], 1):
        text = q.get("text", "")
        target = q.get("target", "")
        n = q.get("interview_number", "?")
        hyp = q.get("hypothesis_id") or "-"
        sens = q.get("sensitivity", "?")
        lines.append(
            f'**#{i}** (인터뷰 #{n:03d} · {target} · {hyp} · 민감도 {sens})\n> "{truncate_field(text, 600)}"'
        )

    return make_info_embed(
        title="💬 인용 검색 결과",
        description=truncate_description("\n\n".join(lines)),
        footer=(
            f"필터: keyword=`{keyword or '-'}`, hypothesis=`{hypothesis_id or '-'}` · "
            "총 " + str(len(quotes)) + "건 중 상위 15건"
        ),
    )


# ---------------------------------------------------------------------
# 공통: 입력 에러
# ---------------------------------------------------------------------
def make_input_error_embed(message: str) -> discord.Embed:
    return make_error_embed(
        title="⚠️ 입력을 확인해 주세요",
        description=message,
    )


# ---------------------------------------------------------------------
# 유틸: description 분할
# ---------------------------------------------------------------------
def _chunk_text(text: str, max_chars: int) -> list[str]:
    """긴 텍스트를 줄 단위로 잘라 max_chars 이하 청크 리스트로."""
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
