"""Code Sentinel Discord UI 헬퍼."""
from __future__ import annotations

import discord

from sd_core.discord.ui import (
    make_info_embed,
    make_warning_embed,
    truncate_description,
)

from code_sentinel.reviewer import (
    ComplianceReport,
    ReviewResult,
    TestSuite,
)


_FOOTER_DISCLAIMER = "⚠️ 코드는 외부 LLM 으로 전송됩니다. 민감 코드는 봇 사용 전 마스킹 필요."


def make_review_embed(result: ReviewResult) -> discord.Embed:
    cost = f"{result.cost_krw:.0f}원 · {result.model_used}"
    if result.fallback_triggered:
        cost += " (폴백)"
    return make_info_embed(
        title="📋 Code Review",
        description=truncate_description(result.text, limit=4000),
        footer=f"비용 ≈ {cost} · {_FOOTER_DISCLAIMER}",
    )


def make_findings_embed(findings_count: int) -> discord.Embed | None:
    """룰 매처 결과 요약 (LLM 결과와 별개로 1개 더 띄워 즉시 인식 가능하게)."""
    if findings_count == 0:
        return None
    return make_warning_embed(
        title=f"🛡 룰베이스 사전 매칭: {findings_count}건",
        description="아래 임베드의 [🛡 Argos 특화 체크] 섹션과 함께 검토하세요.",
    )


def make_test_embed(result: TestSuite) -> discord.Embed:
    return make_info_embed(
        title="📝 테스트 생성 결과",
        description=truncate_description(result.text, limit=4000),
        footer=f"비용 ≈ {result.cost_krw:.0f}원 · {_FOOTER_DISCLAIMER}",
    )


def make_compliance_embed(result: ComplianceReport) -> discord.Embed:
    return make_info_embed(
        title="📋 KISA·법령 정합성 리포트",
        description=truncate_description(result.text, limit=4000),
        footer=f"비용 ≈ {result.cost_krw:.0f}원 · 법률 자문 아님",
    )
