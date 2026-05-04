"""Chief of Staff 위임용 액션 핸들러.

지원 액션:
- ``audit_scan``:    즉시 룰베이스 스캔 실행 (payload 비어도 됨).
- ``audit_feature``: PRD 텍스트 → 법령 매핑. payload={"prd_text": str}.

옵션 B 라 LLM 호출 없음 → cost_krw 항상 0.
"""
from __future__ import annotations

from typing import Any

from sd_core.utils.errors import SecuDeckError

from argos_self_audit.compliance_mapper import ComplianceMapper
from argos_self_audit.dependency_checker import DependencyChecker
from argos_self_audit.repo_scanner import RepoScanner


_MAX_PRD_TEXT = 6000


class AuditInternalHandlers:
    """RepoScanner / DependencyChecker / ComplianceMapper 인스턴스를 공유."""

    def __init__(
        self,
        scanner: RepoScanner,
        dep_checker: DependencyChecker,
        compliance: ComplianceMapper,
    ):
        self.scanner = scanner
        self.dep_checker = dep_checker
        self.compliance = compliance

    # -----------------------------------------------------------------
    async def audit_scan(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        from argos_self_audit.reporter import render_immediate_scan
        scan = await self.scanner.scan_all()
        deps = await self.dep_checker.check(self.scanner.clone_dir)
        report = render_immediate_scan(scan, deps)

        return {
            "ok": True,
            "summary": report.body,
            "cost_krw": 0.0,
            "blocks": [
                {"title": "총 발견", "value": str(scan.total_findings), "inline": True},
                {"title": "CRITICAL", "value": str(scan.critical_count), "inline": True},
                {"title": "스캔 파일", "value": str(scan.scanned_files), "inline": True},
                {
                    "title": "의존성 CVE",
                    "value": (
                        str(len(deps.findings)) if deps.available else "skip (osv-scanner 없음)"
                    ),
                    "inline": True,
                },
            ],
        }

    # -----------------------------------------------------------------
    async def audit_feature(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        from argos_self_audit.reporter import render_feature

        prd_text = (payload.get("prd_text") or "").strip()
        if not prd_text:
            raise SecuDeckError(
                "prd_text 누락",
                user_message="법령 매핑할 PRD 텍스트를 함께 보내 주세요.",
            )
        prd_text = prd_text[:_MAX_PRD_TEXT]

        cmap = self.compliance.map_feature(prd_text)
        report = render_feature(cmap, prd_excerpt=prd_text[:300])
        return {
            "ok": True,
            "summary": report.body,
            "cost_krw": 0.0,
            "blocks": [
                {
                    "title": "매핑된 조항",
                    "value": str(len(cmap.matched_articles)),
                    "inline": True,
                },
                {
                    "title": "위험 시나리오",
                    "value": str(len(cmap.risk_scenarios)),
                    "inline": True,
                },
                {
                    "title": "체크리스트 항목",
                    "value": str(len(cmap.implementation_checklist)),
                    "inline": True,
                },
            ],
        }


__all__ = ["AuditInternalHandlers"]
