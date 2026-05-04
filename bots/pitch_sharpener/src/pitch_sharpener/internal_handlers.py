"""Chief of Staff 가 위임 호출하는 액션 핸들러 모음.

표준 응답 dict (sd_core.discord.internal_api 참조):
    {ok, summary, blocks, cost_krw, error}

라우팅에서 자주 들어올 액션:
- ``pitch_quick``: payload={"document_text": str} → 빠른 진단 (Sonnet 1회).
- ``pitch_focus``: payload={"document_text": str, "persona_id": str} → 단일 페르소나.

풀 리뷰(``pitch_review``)는 6 페르소나 병렬·1~2분 소요라 라우팅 응답에 부적합.
사용자가 직접 ``/pitch review`` 슬래시 커맨드를 쓰도록 둠.
"""
from __future__ import annotations

from typing import Any

from sd_core.utils.errors import SecuDeckError

from pitch_sharpener.review_engine import ReviewEngine


class PitchInternalHandlers:
    """ReviewEngine 한 개 인스턴스를 공유해 슬래시 커맨드와 동일한 비용 추적."""

    def __init__(self, engine: ReviewEngine):
        self.engine = engine

    # -----------------------------------------------------------------
    async def pitch_quick(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        """1분 이내 빠른 진단."""
        document_text = (payload.get("document_text") or "").strip()
        if not document_text:
            raise SecuDeckError(
                "document_text 누락",
                user_message="진단할 사업계획서 본문이 비어 있어요.",
            )
        result = await self.engine.quick_diagnosis(
            document_text=document_text,
            user_id=user_id,
        )
        return {
            "ok": True,
            "summary": result.text,
            "cost_krw": result.cost_krw,
            "blocks": [
                {"title": "모드", "value": "Quick Diagnosis (Sonnet 1회)", "inline": True},
            ],
        }

    # -----------------------------------------------------------------
    async def pitch_focus(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        """단일 페르소나 깊이 리뷰."""
        document_text = (payload.get("document_text") or "").strip()
        persona_id = (payload.get("persona_id") or "").strip()
        if not document_text:
            raise SecuDeckError(
                "document_text 누락",
                user_message="리뷰할 사업계획서 본문이 비어 있어요.",
            )
        if not persona_id:
            # cos 가 페르소나를 지정 못 했을 때는 Customer Voice 가 가장 보편적.
            persona_id = "customer_voice"

        if persona_id not in self.engine.persona_by_id:
            available = ", ".join(self.engine.persona_by_id.keys())
            raise SecuDeckError(
                f"unknown persona_id: {persona_id}",
                user_message=f"'{persona_id}' 페르소나는 등록돼 있지 않아요. 사용 가능: {available}",
            )

        result = await self.engine.focused_review(
            document_text=document_text,
            persona_id=persona_id,
            user_id=user_id,
        )
        review = result.persona_review
        return {
            "ok": True,
            "summary": review.content,
            "cost_krw": review.cost_krw,
            "blocks": [
                {
                    "title": "페르소나",
                    "value": f"{review.persona_emoji} {review.persona_name}",
                    "inline": True,
                },
                {
                    "title": "폴백",
                    "value": "발생" if review.fallback_triggered else "없음",
                    "inline": True,
                },
            ],
        }


__all__ = ["PitchInternalHandlers"]
