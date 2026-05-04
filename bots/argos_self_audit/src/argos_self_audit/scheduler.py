"""매일 03:00 KST cron 트리거 — discord.py ``tasks.loop`` 기반.

discord.py 의 ``tasks.loop(time=...)`` 는 UTC 기준이라 한국 시간 03:00 = UTC 18:00 (전일).
``zoneinfo.ZoneInfo("Asia/Seoul")`` 로 명시적으로 KST 지정해 혼동 방지.

설계 결정:
- 봇 재시작·deploy 시점에 따라 첫 실행이 늦어질 수 있음 → 부팅 직후 1회 즉시 실행 옵션 (``RUN_ON_START``).
- 실행 중 예외는 다음 cycle 까지 누적되지 않게 광범위 except + 로그.
- 테스트·디버깅용 즉시 트리거 메서드 ``trigger_now()`` 노출.
"""
from __future__ import annotations

import os
from datetime import time as dtime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from sd_core.utils.logger import get_logger

from argos_self_audit.dependency_checker import DependencyChecker
from argos_self_audit.repo_scanner import RepoScanner
from argos_self_audit.reporter import render_daily
from argos_self_audit.ui import make_report_embed, mention_role_if_critical


_log = get_logger("argos_self_audit.scheduler")

# KST 03:00 — 트래픽 한가하고 야간 빌드 직후라 fresh state.
_DAILY_HOUR_KST = 3
_DAILY_MIN_KST = 0
_KST = ZoneInfo("Asia/Seoul")


class AuditScheduler(commands.Cog):
    """일일 cron 코그.

    부팅 시 ``cog_load`` 에서 loop 시작. 봇 종료 시 ``cog_unload`` 에서 자동 정리.
    """

    def __init__(
        self,
        bot: discord.Client,
        scanner: RepoScanner,
        dep_checker: DependencyChecker,
        *,
        channel_id: int | None,
        dev_role_id: int | None = None,
        run_on_start: bool = False,
    ):
        self.bot = bot
        self.scanner = scanner
        self.dep_checker = dep_checker
        self.channel_id = channel_id
        self.dev_role_id = dev_role_id
        self.run_on_start = run_on_start
        # last 24h PR 결과 누적 (메모리). webhook 핸들러가 append 하고 daily 가 인용.
        self.recent_pr_reports: list[str] = []

    async def cog_load(self) -> None:  # discord.py 2.x 라이프사이클
        if not self.channel_id:
            _log.warning("scheduler_disabled_no_channel")
            return
        self.daily_scan.start()
        if self.run_on_start:
            _log.info("scheduler_run_on_start_scheduled")

    async def cog_unload(self) -> None:
        if self.daily_scan.is_running():
            self.daily_scan.cancel()

    # -----------------------------------------------------------------
    @tasks.loop(time=dtime(hour=_DAILY_HOUR_KST, minute=_DAILY_MIN_KST, tzinfo=_KST))
    async def daily_scan(self) -> None:
        await self._run_and_post()

    @daily_scan.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()
        if self.run_on_start:
            _log.info("scheduler_initial_run")
            try:
                await self._run_and_post()
            except Exception as exc:  # noqa: BLE001 — 부팅 직후 실패는 다음 cron 으로 회복
                _log.warning("initial_scan_failed", error=str(exc))

    # -----------------------------------------------------------------
    async def _run_and_post(self) -> None:
        """스캔 실행 + 채널 게시. 예외는 모두 잡아 로그만."""
        try:
            scan = await self.scanner.scan_all()
            deps = await self.dep_checker.check(self.scanner.clone_dir)
            report = render_daily(scan, deps)
        except Exception as exc:  # noqa: BLE001
            _log.exception("daily_scan_failed", error=str(exc))
            return

        channel = self.bot.get_channel(self.channel_id) if self.channel_id else None
        if channel is None:
            _log.warning("daily_scan_channel_missing", channel_id=self.channel_id)
            return

        embed = make_report_embed(report)
        prefix = mention_role_if_critical(report.severity, self.dev_role_id)
        try:
            await channel.send(content=prefix or None, embed=embed)
            _log.info(
                "daily_report_posted",
                severity=report.severity,
                critical=scan.critical_count,
                channel_id=self.channel_id,
            )
        except discord.HTTPException as exc:
            _log.warning("daily_report_send_failed", error=str(exc))

    async def trigger_now(self) -> None:
        """``/audit scan`` 또는 운영 디버깅용 즉시 트리거."""
        await self._run_and_post()


def read_channel_id_from_env() -> int | None:
    raw = os.getenv("SELF_AUDIT_CHANNEL_ID")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        _log.warning("invalid_channel_id_env", value=raw)
        return None


def read_dev_role_id_from_env() -> int | None:
    raw = os.getenv("SELF_AUDIT_DEV_ROLE_ID")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


__all__ = [
    "AuditScheduler",
    "read_channel_id_from_env",
    "read_dev_role_id_from_env",
]
