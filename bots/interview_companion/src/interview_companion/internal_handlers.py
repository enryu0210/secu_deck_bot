"""Chief of Staff 위임용 액션 핸들러.

지원 액션:
- ``interview_prep``: 인터뷰이 정보로 가이드 생성.
    payload={"name": str, "role": str, "company": str, "company_size": str,
             "background": str?, "focus_ids": [str] | None}
- ``interview_insight``: 누적 인터뷰 분석.
    payload={} — user_id 기준 모든 기록 분석.

저장(``interview_log``)은 사용자 직접 슬래시 커맨드로 (긴 raw_notes 입력 + 모달 UI 필요).
"""
from __future__ import annotations

from typing import Any

from sd_core.utils.errors import SecuDeckError

from interview_companion.insight_extractor import InsightExtractor
from interview_companion.interview_prep import InterviewPrep
from interview_companion.storage import InterviewTarget


class InterviewInternalHandlers:
    def __init__(self, prep: InterviewPrep, insight: InsightExtractor):
        self.prep = prep
        self.insight = insight

    # -----------------------------------------------------------------
    async def interview_prep(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        # 필수 필드 검증 — 익명화 권장이라 name 은 별칭/이니셜이어도 OK.
        name = str(payload.get("name") or "").strip()
        role = str(payload.get("role") or "").strip()
        company = str(payload.get("company") or "").strip()
        size = str(payload.get("company_size") or "").strip()
        if not (name and role and company and size):
            raise SecuDeckError(
                "interview target 필드 누락",
                user_message=(
                    "인터뷰 가이드를 만들려면 name·role·company·company_size 가 모두 필요해요. "
                    "예: '대표 A, CISO, 웰컴저축은행, 200인 이하'"
                ),
            )

        target = InterviewTarget(
            name=name,
            role=role,
            company=company,
            company_size=size,
            background=str(payload.get("background") or ""),
        )
        focus_raw = payload.get("focus_ids")
        focus_ids: list[str] | None = None
        if isinstance(focus_raw, list):
            focus_ids = [str(x) for x in focus_raw if x]

        guide = await self.prep.generate_guide(
            target=target,
            focus_ids=focus_ids,
            user_id=user_id,
        )
        return {
            "ok": True,
            "summary": guide.text,
            "cost_krw": guide.cost_krw,
            "blocks": [
                {"title": "대상", "value": target.display, "inline": False},
                {
                    "title": "집중 가설",
                    "value": ", ".join(guide.focused_hypotheses) or "(자동 priority 1)",
                    "inline": False,
                },
            ],
        }

    # -----------------------------------------------------------------
    async def interview_insight(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        report = await self.insight.analyze_all(user_id=user_id)
        return {
            "ok": True,
            "summary": report.text,
            "cost_krw": report.cost_krw,
            "blocks": [
                {"title": "분석 인터뷰 수", "value": str(report.interview_count), "inline": True},
            ],
        }


__all__ = ["InterviewInternalHandlers"]
