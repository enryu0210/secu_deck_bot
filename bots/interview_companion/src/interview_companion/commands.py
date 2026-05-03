"""슬래시 커맨드 그룹 ``/interview``.

- /interview prep    : 인터뷰 가이드 생성 (Sonnet 1회)
- /interview log     : 인터뷰 기록·정리 (Flash + Sonnet, Postgres 저장)
- /interview insight : 누적 분석 (Gemini Flash 1회, 1M 컨텍스트)
- /interview quotes  : 인용 검색 (LLM 불필요)
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from sd_core.utils.errors import SecuDeckError
from sd_core.utils.logger import get_logger

from interview_companion.insight_extractor import InsightExtractor
from interview_companion.interview_logger import InterviewLogger
from interview_companion.interview_prep import InterviewPrep
from interview_companion.storage import InterviewStorage, InterviewTarget
from interview_companion.ui import (
    make_guide_embed,
    make_input_error_embed,
    make_insight_embeds,
    make_log_embeds,
    make_quotes_embed,
)


if TYPE_CHECKING:  # 순환 import 방지
    from sd_core.discord.base_bot import SecuDeckBot


_log = get_logger("interview_companion.commands")


# 첨부파일에서 텍스트로 변환할 때 허용 확장자
_TEXT_EXTS = {".txt", ".md", ".log"}
_MAX_RAW_CHARS = 80_000  # 약 1.5만 토큰. Gemini Flash 안전 범위.


class InterviewCommands(app_commands.Group):
    """``/interview`` 슬래시 커맨드 그룹."""

    def __init__(
        self,
        prep: InterviewPrep,
        logger: InterviewLogger,
        insights: InsightExtractor,
        storage: InterviewStorage,
    ):
        super().__init__(name="interview", description="고객 인터뷰 가이드·기록·분석")
        self.prep = prep
        self.logger = logger
        self.insights = insights
        self.storage = storage

    # -----------------------------------------------------------------
    @app_commands.command(name="prep", description="인터뷰 가이드 생성 (약 30초)")
    @app_commands.describe(
        target_name="인터뷰이 식별 (이니셜·역할 권장, 실명 비권장)",
        target_role="역할/직책",
        target_company="회사 (익명화 가능: A보험 등)",
        company_size="회사 규모 (예: 30인, 100인 이하)",
        background="사전 정보·이번 인터뷰 목적",
        focus="집중 가설 ID 콤마 구분 (예: H1_subcontractor_risk,H4_compliance_report_burden). 비우면 자동 선택.",
    )
    async def prep_cmd(
        self,
        interaction: discord.Interaction,
        target_name: str,
        target_role: str,
        target_company: str,
        company_size: str,
        background: str = "",
        focus: str = "",
    ):
        await interaction.response.defer(thinking=True)

        target = InterviewTarget(
            name=target_name.strip(),
            role=target_role.strip(),
            company=target_company.strip(),
            company_size=company_size.strip(),
            background=background.strip(),
        )
        focus_ids = [s.strip() for s in focus.split(",") if s.strip()] or None

        guide = await self.prep.generate_guide(
            target=target,
            focus_ids=focus_ids,
            user_id=str(interaction.user.id),
        )
        await interaction.followup.send(
            embed=make_guide_embed(guide.text, guide.focused_hypotheses, guide.cost_krw)
        )

    # -----------------------------------------------------------------
    @app_commands.command(name="log", description="인터뷰 기록·정리 + 저장 (약 60초)")
    @app_commands.describe(
        target_name="인터뷰이 식별 (이전 prep 과 동일 권장)",
        target_role="역할/직책",
        target_company="회사",
        company_size="회사 규모",
        date_str="인터뷰 날짜 YYYY-MM-DD (비우면 오늘)",
        notes="첨부 (TXT/MD/LOG)",
        text="첨부 대신 직접 입력",
    )
    async def log_cmd(
        self,
        interaction: discord.Interaction,
        target_name: str,
        target_role: str,
        target_company: str,
        company_size: str,
        date_str: str = "",
        notes: discord.Attachment | None = None,
        text: str | None = None,
    ):
        await interaction.response.defer(thinking=True)

        # 1) 입력 검증
        try:
            interview_date = _parse_date(date_str) if date_str else date.today()
        except ValueError as exc:
            await interaction.followup.send(
                embed=make_input_error_embed(
                    f"날짜 형식이 올바르지 않아요: {exc}\n예) 2026-04-15"
                ),
                ephemeral=True,
            )
            return

        try:
            raw = await _gather_raw_content(notes, text)
        except ValueError as exc:
            await interaction.followup.send(
                embed=make_input_error_embed(str(exc)),
                ephemeral=True,
            )
            return

        target = InterviewTarget(
            name=target_name.strip(),
            role=target_role.strip(),
            company=target_company.strip(),
            company_size=company_size.strip(),
        )

        result = await self.logger.log(
            target=target,
            interview_date=interview_date,
            raw_content=raw,
            user_id=str(interaction.user.id),
        )

        embeds = make_log_embeds(
            interview_number=result.record.interview_number,
            target_display=target.display,
            summary=result.record.summary,
            hypotheses_results=result.record.hypotheses_results,
            quotes=result.record.quotes,
            cost_krw=result.cost_krw,
            parse_warning=result.parse_warning,
        )
        await interaction.followup.send(embeds=embeds[:10])

    # -----------------------------------------------------------------
    @app_commands.command(name="insight", description="누적 인터뷰 패턴 분석 (약 90초)")
    async def insight_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            report = await self.insights.analyze_all(user_id=str(interaction.user.id))
        except SecuDeckError as exc:
            await interaction.followup.send(exc.user_message, ephemeral=True)
            return
        await interaction.followup.send(
            embeds=make_insight_embeds(report.text, report.interview_count, report.cost_krw)
        )

    # -----------------------------------------------------------------
    @app_commands.command(name="quotes", description="저장된 인용 발언 검색")
    @app_commands.describe(
        keyword="텍스트 키워드 (선택)",
        hypothesis="가설 ID 필터 (예: H1_subcontractor_risk, 선택)",
    )
    async def quotes_cmd(
        self,
        interaction: discord.Interaction,
        keyword: str = "",
        hypothesis: str = "",
    ):
        await interaction.response.defer(thinking=True)
        results = await self.storage.search_quotes(
            user_id=str(interaction.user.id),
            keyword=keyword or None,
            hypothesis_id=hypothesis or None,
        )
        await interaction.followup.send(
            embed=make_quotes_embed(results, keyword or None, hypothesis or None)
        )


# ---------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------
def _parse_date(s: str) -> date:
    """YYYY-MM-DD 만 허용. 다른 포맷은 명확히 에러."""
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("YYYY-MM-DD 형식이어야 해요") from exc


async def _gather_raw_content(
    attachment: discord.Attachment | None,
    text: str | None,
) -> str:
    """첨부 또는 직접 입력 → 단일 문자열. 둘 다 없으면 에러."""
    if attachment is not None:
        ext = ("." + attachment.filename.rsplit(".", 1)[-1].lower()) if "." in attachment.filename else ""
        if ext not in _TEXT_EXTS:
            raise ValueError(
                f"지원 안 하는 파일 형식이에요: {attachment.filename}\n"
                f"지원: {', '.join(sorted(_TEXT_EXTS))}"
            )
        data = await attachment.read()
        try:
            decoded = data.decode("utf-8")
        except UnicodeDecodeError:
            decoded = data.decode("cp949", errors="replace")
        if len(decoded) > _MAX_RAW_CHARS:
            decoded = decoded[:_MAX_RAW_CHARS] + "\n\n[...본문 절단됨 — 너무 길어요...]"
        return decoded

    if text is not None and text.strip():
        if len(text) > _MAX_RAW_CHARS:
            return text[:_MAX_RAW_CHARS] + "\n\n[...본문 절단됨...]"
        return text

    raise ValueError("녹취/메모 첨부 또는 텍스트 입력 중 하나는 필수예요.")


def install_commands(
    bot: "SecuDeckBot",
    prep: InterviewPrep,
    logger: InterviewLogger,
    insights: InsightExtractor,
    storage: InterviewStorage,
) -> None:
    """봇 트리에 ``/interview`` 그룹을 등록."""
    bot.tree.add_command(InterviewCommands(prep, logger, insights, storage))
