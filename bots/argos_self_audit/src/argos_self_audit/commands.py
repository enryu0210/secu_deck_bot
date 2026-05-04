"""슬래시 커맨드 그룹 ``/audit`` — scan / feature / report 3종.

LLM 호출 없음. 모든 응답은 룰베이스/키워드 매핑 결과를 템플릿으로 포매팅.
"""
from __future__ import annotations

import datetime as dt

import discord
from discord import app_commands

from sd_core.utils.errors import SecuDeckError
from sd_core.utils.logger import get_logger

from argos_self_audit.compliance_mapper import ComplianceMapper
from argos_self_audit.dependency_checker import DependencyChecker
from argos_self_audit.repo_scanner import RepoScanner
from argos_self_audit.reporter import (
    render_feature,
    render_immediate_scan,
)
from argos_self_audit.scheduler import AuditScheduler
from argos_self_audit.ui import make_report_embed, make_unavailable_embed


_log = get_logger("argos_self_audit.commands")

# /audit feature 입력 텍스트 상한. PRD 본문이 너무 길면 키워드 매핑 정밀도가 떨어지지 않으므로
# 디스코드 슬래시 옵션 길이 한계만 신경쓰면 됨 — 6KB 정도가 임베드 표기 안전선.
_MAX_PRD_TEXT = 6000

# /audit feature 첨부 파일 한계. 텍스트만 받음.
_MAX_PRD_ATTACHMENT_BYTES = 200 * 1024


async def _read_prd_attachment(attachment: discord.Attachment) -> str:
    """텍스트 첨부만 허용 — PDF/DOCX 는 의존성 폭발 회피 위해 명시적 거부."""
    name = (attachment.filename or "").lower()
    if name.endswith((".pdf", ".docx")):
        raise SecuDeckError(
            "PDF/DOCX 첨부 미지원",
            user_message="PRD 는 .md / .txt 파일만 첨부해 주세요. (또는 `text` 필드에 직접 입력)",
        )
    if attachment.size > _MAX_PRD_ATTACHMENT_BYTES:
        raise SecuDeckError(
            "첨부 너무 큼",
            user_message="PRD 첨부는 200KB 이하만 지원해요.",
        )
    raw = await attachment.read()
    for enc in ("utf-8", "utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


class AuditCommands(app_commands.Group):
    def __init__(
        self,
        scanner: RepoScanner,
        dep_checker: DependencyChecker,
        compliance: ComplianceMapper,
        scheduler: AuditScheduler,
    ):
        super().__init__(name="audit", description="Argos 자가 검증 (룰베이스 + 키워드 매핑)")
        self.scanner = scanner
        self.dep_checker = dep_checker
        self.compliance = compliance
        self.scheduler = scheduler
        # 누적 즉시 스캔 결과를 메모리에 보관 — /audit report 가 합산.
        self._monthly_scan_count = 0
        self._monthly_critical_count = 0
        self._month_started_at = dt.date.today().replace(day=1)

    # -----------------------------------------------------------------
    @app_commands.command(name="scan", description="즉시 코드베이스 스캔 실행")
    async def scan(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            scan = await self.scanner.scan_all()
            deps = await self.dep_checker.check(self.scanner.clone_dir)
        except SecuDeckError as exc:
            await interaction.followup.send(exc.user_message, ephemeral=True)
            return

        self._tick_monthly(scan.critical_count)
        report = render_immediate_scan(scan, deps)
        await interaction.followup.send(embed=make_report_embed(report))

    # -----------------------------------------------------------------
    @app_commands.command(
        name="feature",
        description="신규 기능 컴플라이언스 매핑 (PRD 텍스트 → 법령 매핑)",
    )
    @app_commands.describe(
        text="PRD 본문 직접 입력",
        attachment=".md/.txt 파일 첨부 (text 와 둘 중 하나)",
    )
    async def feature(
        self,
        interaction: discord.Interaction,
        text: str | None = None,
        attachment: discord.Attachment | None = None,
    ):
        await interaction.response.defer(thinking=True)
        if not text and attachment is None:
            await interaction.followup.send(
                "PRD 본문을 `text` 로 직접 입력하거나 .md/.txt 파일을 첨부해 주세요.",
                ephemeral=True,
            )
            return

        prd_text = text or ""
        if attachment is not None:
            try:
                prd_text = await _read_prd_attachment(attachment)
            except SecuDeckError as exc:
                await interaction.followup.send(exc.user_message, ephemeral=True)
                return

        prd_text = prd_text[:_MAX_PRD_TEXT]
        cmap = self.compliance.map_feature(prd_text)
        report = render_feature(cmap, prd_excerpt=prd_text[:300])
        await interaction.followup.send(embed=make_report_embed(report))

    # -----------------------------------------------------------------
    @app_commands.command(
        name="report",
        description="이번 달 self-audit 종합 리포트 (간이)",
    )
    async def report(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        embed = self._monthly_summary_embed()
        await interaction.followup.send(embed=embed)

    # -----------------------------------------------------------------
    def _tick_monthly(self, critical_in_this_scan: int) -> None:
        today = dt.date.today()
        # 월이 바뀌면 카운터 리셋.
        if today.replace(day=1) != self._month_started_at:
            self._monthly_scan_count = 0
            self._monthly_critical_count = 0
            self._month_started_at = today.replace(day=1)
        self._monthly_scan_count += 1
        self._monthly_critical_count += critical_in_this_scan

    def _monthly_summary_embed(self) -> discord.Embed:
        from argos_self_audit.reporter import RenderedReport

        body = "\n".join([
            f"**{self._month_started_at.strftime('%Y-%m')} 종합**",
            "",
            f"- 즉시 스캔 실행: **{self._monthly_scan_count}회**",
            f"- 누적 CRITICAL 발견: **{self._monthly_critical_count}건**",
            "",
            "_(이 리포트는 봇 메모리 기반 간이 집계입니다. 봇 재시작 시 카운터가 초기화됩니다."
            " 정밀 통계는 Postgres 도입 시 추가 예정.)_",
        ])
        return make_report_embed(RenderedReport(
            title="📊 Self-Audit 월간 리포트",
            body=body,
            severity="WARN" if self._monthly_critical_count else "INFO",
            footer="간이 집계 — 정밀 데이터는 #self-audit 채널 일일 게시물 참조.",
        ))


def install_commands(
    bot,
    scanner: RepoScanner,
    dep_checker: DependencyChecker,
    compliance: ComplianceMapper,
    scheduler: AuditScheduler,
) -> None:
    bot.tree.add_command(AuditCommands(scanner, dep_checker, compliance, scheduler))


__all__ = ["install_commands", "AuditCommands"]
