"""GitHub PR 머지 webhook 수신·검증·Code Sentinel 위임 · 디스코드 게시.

InternalAPIServer 의 ``add_route_hook`` 으로 ``/webhook/github`` 라우트를 등록.
같은 포트에 cos 위임용 ``/api/invoke`` 와 공존하지만, 인증 방식은 다름:

- ``/api/invoke``: ``X-Internal-Secret`` 공유 시크릿 (5봇 공통)
- ``/webhook/github``: ``X-Hub-Signature-256`` HMAC-SHA256 (GitHub webhook secret)

GitHub 가 보내는 HMAC 은 raw body 에 대해 계산되므로, FastAPI 에서 ``Request.body()``
원본 바이트를 받아 검증한 뒤에 JSON 파싱.

PR merged 이벤트만 처리. open/sync/close(merged=False) 는 무시.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any

import discord
# fastapi 심볼은 반드시 module top-level 에서 import 한다.
# 이유: `from __future__ import annotations` 가 켜져 있어 타입 힌트가 문자열로
# 보관되는데, FastAPI 가 시그니처를 해석할 때 함수의 ``__globals__``(=모듈 globals)
# 에서 이름을 찾는다. ``install()`` 안에서 lazy import 하면 ``Request`` 가 모듈
# globals 에 없어서 FastAPI 가 ``request`` 를 일반 쿼리 파라미터로 오해한다
# (실제로 GitHub webhook 호출 시 422 "Field required: query.request" 반환).
from fastapi import Header, HTTPException, Request

from sd_core.discord.internal_client import InternalAPIClient
from sd_core.utils.errors import SecuDeckError
from sd_core.utils.logger import get_logger

from argos_self_audit.compliance_mapper import ComplianceMapper
from argos_self_audit.reporter import render_pr_review
from argos_self_audit.ui import make_report_embed, mention_role_if_critical


_log = get_logger("argos_self_audit.github_webhook")

# Code Sentinel 위임 액션 — internal_handlers.code_review 와 동기화 유지.
_DELEGATE_BOT = "code_sentinel"
_DELEGATE_ACTION = "code_review"

# Code Sentinel 호출 시 보낼 코드 본문 길이 상한 (cos delegator 와 같은 8KB).
_MAX_DIFF_FOR_DELEGATE = 8000


class GitHubWebhookHandler:
    """webhook 수신·검증·디스패치 컨테이너."""

    def __init__(
        self,
        bot: discord.Client,
        *,
        webhook_secret: str,
        channel_id: int | None,
        dev_role_id: int | None,
        compliance_mapper: ComplianceMapper,
        internal_client: InternalAPIClient | None = None,
    ):
        self.bot = bot
        self.secret_bytes = webhook_secret.encode("utf-8") if webhook_secret else b""
        self.channel_id = channel_id
        self.dev_role_id = dev_role_id
        self.compliance = compliance_mapper
        # 같은 INTERNAL_API_SECRET 으로 Code Sentinel 호출.
        self.client = internal_client or InternalAPIClient()

    # -----------------------------------------------------------------
    # FastAPI 라우트 훅 — InternalAPIServer.add_route_hook 에 전달
    # -----------------------------------------------------------------
    def install(self, app: Any) -> None:
        handler = self

        @app.post("/webhook/github")
        async def github_webhook(
            request: Request,
            x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
            x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
        ) -> dict[str, Any]:
            raw = await request.body()

            if not handler.secret_bytes:
                raise HTTPException(status_code=503, detail="GITHUB_WEBHOOK_SECRET 미설정")
            if not handler._verify_signature(raw, x_hub_signature_256):
                _log.warning("webhook_signature_mismatch")
                raise HTTPException(status_code=401, detail="signature 불일치")

            # ping 이벤트는 즉시 200 (GitHub 가 webhook 등록 시 보냄).
            if x_github_event == "ping":
                return {"ok": True, "event": "ping"}

            if x_github_event != "pull_request":
                return {"ok": True, "event": x_github_event, "skipped": True}

            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise HTTPException(status_code=400, detail="JSON 파싱 실패")

            # merged PR 만 처리.
            action = payload.get("action")
            pr = payload.get("pull_request") or {}
            if action != "closed" or not pr.get("merged"):
                return {"ok": True, "skipped": True, "reason": "not a merge"}

            # 게시 작업은 background — webhook 응답 즉시 200 반환 (GitHub 10s 타임아웃 회피).
            asyncio.create_task(handler._process_merged_pr(pr))
            return {"ok": True, "queued": True, "pr": pr.get("number")}

    # -----------------------------------------------------------------
    def _verify_signature(self, raw: bytes, signature_header: str | None) -> bool:
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        sent = signature_header[7:]
        mac = hmac.new(self.secret_bytes, msg=raw, digestmod=hashlib.sha256)
        expected = mac.hexdigest()
        return hmac.compare_digest(sent, expected)

    # -----------------------------------------------------------------
    async def _process_merged_pr(self, pr: dict[str, Any]) -> None:
        """Code Sentinel 위임 + 컴플라이언스 매핑 + 디스코드 게시."""
        pr_url = str(pr.get("html_url") or "")
        pr_title = str(pr.get("title") or "")
        pr_branch = str((pr.get("head") or {}).get("ref") or "?")
        pr_body = str(pr.get("body") or "")

        # 1) Code Sentinel 위임 — diff 본문 대신 PR 메타·제목·body 로 대체.
        #    (실제 diff fetch 는 Code Sentinel 의 GitHubFetcher 가 PR URL 로 처리하지만,
        #     internal API 는 code 텍스트를 받음 → PR URL 을 코드 영역에 넣어 컨텍스트 유지)
        delegate_payload = {
            "code": _build_delegate_code(pr_url, pr_title, pr_branch, pr_body),
            "language": "diff",
            "focus": "security",
        }

        sentinel_summary = ""
        sentinel_findings = 0
        try:
            res = await self.client.invoke(
                bot=_DELEGATE_BOT,
                action=_DELEGATE_ACTION,
                payload=delegate_payload,
                user_id="argos_self_audit_webhook",
            )
            sentinel_summary = str(res.get("summary") or "")
            # blocks 중 "룰베이스 발견" 카운트가 있으면 사용.
            for b in res.get("blocks") or []:
                if str(b.get("title")).startswith("룰베이스"):
                    try:
                        sentinel_findings = int(b.get("value") or 0)
                    except (TypeError, ValueError):
                        sentinel_findings = 0
        except SecuDeckError as exc:
            sentinel_summary = f"_(Code Sentinel 호출 실패: {exc.user_message})_"
            _log.warning("sentinel_delegate_failed", error=str(exc))

        # 2) 컴플라이언스 매핑 — PR 본문 + 제목으로 키워드 검사.
        compliance = self.compliance.map_feature(f"{pr_title}\n\n{pr_body}")

        # 3) 리포트 + 게시
        report = render_pr_review(
            pr_url=pr_url,
            pr_title=pr_title,
            pr_branch=pr_branch,
            sentinel_summary=sentinel_summary,
            sentinel_findings_count=sentinel_findings,
            compliance=compliance,
        )

        if not self.channel_id:
            _log.warning("webhook_no_channel_configured")
            return
        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            _log.warning("webhook_channel_not_found", channel_id=self.channel_id)
            return
        embed = make_report_embed(report)
        prefix = mention_role_if_critical(report.severity, self.dev_role_id)
        try:
            await channel.send(content=prefix or None, embed=embed)
            _log.info(
                "pr_review_posted",
                pr=pr.get("number"),
                severity=report.severity,
                sentinel_findings=sentinel_findings,
            )
        except discord.HTTPException as exc:
            _log.warning("pr_review_send_failed", error=str(exc))


def _build_delegate_code(pr_url: str, title: str, branch: str, body: str) -> str:
    """Code Sentinel 의 code_review 핸들러가 받는 ``code`` 필드 구성.

    실제 diff 를 GitHub 에서 다시 fetch 하지 않고, PR 메타·body 만 보내 비용 최소화.
    Code Sentinel 의 RuleMatcher 는 정규식 기반이라 PR body 에 첨부된 코드 블록도 함께 본다.
    """
    snippet = (
        f"# PR Auto-Review (via Argos Self-Audit webhook)\n"
        f"# url: {pr_url}\n"
        f"# branch: {branch}\n"
        f"# title: {title}\n\n"
        f"## PR description\n{body or '(없음)'}\n"
    )
    if len(snippet) > _MAX_DIFF_FOR_DELEGATE:
        snippet = snippet[: _MAX_DIFF_FOR_DELEGATE] + "\n# ...절단..."
    return snippet


__all__ = ["GitHubWebhookHandler"]
