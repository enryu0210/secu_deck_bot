"""Argos Self-Audit 봇 엔트리포인트.

실행:
    uv run python -m argos_self_audit.main

환경변수 (README 참조):
    DISCORD_BOT_TOKEN_AUDIT     (필수)
    INTERNAL_API_SECRET         (필수 — cos 위임 + Code Sentinel 호출)
    BOT_URL_CODE                (필수 — webhook 의 Code Sentinel 위임용)
    SELF_AUDIT_CHANNEL_ID       (필수)
    ARGOS_REPO_URL              (필수)
    GITHUB_PAT_AUDIT            (필수 — repo clone 용)
    GITHUB_WEBHOOK_SECRET       (필수)
    SELF_AUDIT_DEV_ROLE_ID      (선택)
    DISCORD_GUILD_ID            (선택 — 슬래시 즉시 동기화)
    AUDIT_RUN_ON_START          (선택 — "1" 이면 부팅 직후 1회 실행)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from sd_core.discord.base_bot import SecuDeckBot
from sd_core.discord.internal_api import InternalAPIServer
from sd_core.discord.internal_client import InternalAPIClient
from sd_core.utils.errors import ConfigError
from sd_core.utils.logger import get_logger

from argos_self_audit.commands import install_commands
from argos_self_audit.compliance_mapper import ComplianceMapper
from argos_self_audit.dependency_checker import DependencyChecker
from argos_self_audit.github_webhook import GitHubWebhookHandler
from argos_self_audit.internal_handlers import AuditInternalHandlers
from argos_self_audit.repo_scanner import RepoScanner, default_clone_dir
from argos_self_audit.scheduler import (
    AuditScheduler,
    read_channel_id_from_env,
    read_dev_role_id_from_env,
)


load_dotenv()

_log = get_logger("argos_self_audit.main")

_BOT_ROOT = Path(__file__).resolve().parents[2]
_CHECKS_DIR = _BOT_ROOT / "checks"


async def _async_main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN_AUDIT")
    if not token:
        raise ConfigError("DISCORD_BOT_TOKEN_AUDIT 환경변수가 비어 있습니다.")

    repo_url = os.getenv("ARGOS_REPO_URL")
    if not repo_url:
        raise ConfigError("ARGOS_REPO_URL 환경변수가 비어 있습니다.")

    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not webhook_secret:
        # 부팅은 허용하지만 webhook 라우트는 503 반환됨 (보안 사고 차단).
        _log.warning("github_webhook_secret_missing — webhook 비활성")

    bot = SecuDeckBot(bot_name="argos_self_audit")

    # -----------------------------------------------------------------
    # 핵심 컴포넌트 와이어링
    # -----------------------------------------------------------------
    scanner = RepoScanner(
        checks_dir=_CHECKS_DIR,
        repo_url=repo_url,
        clone_dir=default_clone_dir(),
        github_pat=os.getenv("GITHUB_PAT_AUDIT"),
    )
    dep_checker = DependencyChecker()
    compliance = ComplianceMapper(_CHECKS_DIR / "pipa_articles.yaml")

    channel_id = read_channel_id_from_env()
    dev_role_id = read_dev_role_id_from_env()
    run_on_start = os.getenv("AUDIT_RUN_ON_START", "").strip() in ("1", "true", "TRUE")

    scheduler = AuditScheduler(
        bot=bot,
        scanner=scanner,
        dep_checker=dep_checker,
        channel_id=channel_id,
        dev_role_id=dev_role_id,
        run_on_start=run_on_start,
    )
    await bot.add_cog(scheduler)   # discord.py 2.x — add_cog 는 awaitable

    install_commands(bot, scanner, dep_checker, compliance, scheduler)

    # -----------------------------------------------------------------
    # cos 위임용 internal API + GitHub webhook 라우트 훅
    # -----------------------------------------------------------------
    handlers = AuditInternalHandlers(scanner, dep_checker, compliance)
    api = InternalAPIServer(bot_name="argos_self_audit")
    api.register("audit_scan", handlers.audit_scan)
    api.register("audit_feature", handlers.audit_feature)

    if webhook_secret:
        webhook = GitHubWebhookHandler(
            bot=bot,
            webhook_secret=webhook_secret,
            channel_id=channel_id,
            dev_role_id=dev_role_id,
            compliance_mapper=compliance,
            internal_client=InternalAPIClient(),
        )
        api.add_route_hook(webhook.install)

    _log.info(
        "starting_argos_self_audit",
        repo=repo_url,
        channel_id=channel_id,
        run_on_start=run_on_start,
        osv_available=dep_checker.is_available(),
        guild_sync=bot._sync_guild_id,
    )
    async with bot:
        await api.start()
        try:
            await bot.start_with_backoff(token)
        finally:
            await api.stop()


def main() -> None:
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        _log.info("shutdown_keyboard_interrupt")


if __name__ == "__main__":
    main()
