"""Chief of Staff 위임용 액션 핸들러.

지원 액션:
- ``code_review``: payload={"code": str, "language": str?, "focus": "general"|"security"|None}
- ``code_test``:   payload={"code": str, "language": str?}
- ``code_kisa``:   payload={"feature_description": str}

언어 미지정 시 ``LanguageDetector`` 가 자동 감지.
"""
from __future__ import annotations

from typing import Any

from sd_core.utils.errors import SecuDeckError

from code_sentinel.language_detector import detect_language
from code_sentinel.reviewer import CodeReviewer


# Discord 메시지·임베드 description 4096 한계. 코드 6KB 정도가 LLM 입력에도 적합.
_MAX_CODE_LEN = 8000


def _truncate(code: str) -> str:
    if len(code) <= _MAX_CODE_LEN:
        return code
    return code[: _MAX_CODE_LEN - 200] + "\n\n# ... 본문 절단됨 ..."


class CodeInternalHandlers:
    """CodeReviewer 인스턴스를 공유."""

    def __init__(self, reviewer: CodeReviewer):
        self.reviewer = reviewer

    # -----------------------------------------------------------------
    async def code_review(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        code = (payload.get("code") or "").strip()
        if not code:
            raise SecuDeckError(
                "code 누락",
                user_message="리뷰할 코드를 함께 보내 주세요.",
            )
        language = (payload.get("language") or "").strip() or detect_language(code)
        # focus 는 "security" 일 때만 보안 프롬프트로 전환. 그 외는 general.
        focus_raw = payload.get("focus")
        focus = focus_raw if focus_raw in ("security", "general") else None

        result = await self.reviewer.review(
            code=_truncate(code),
            language=language,
            focus=focus,
            user_id=user_id,
        )
        return {
            "ok": True,
            "summary": result.text,
            "cost_krw": result.cost_krw,
            "blocks": [
                {"title": "언어", "value": language or "auto", "inline": True},
                {"title": "포커스", "value": focus or "general", "inline": True},
                {"title": "모델", "value": result.model_used, "inline": True},
                {
                    "title": "룰베이스 발견",
                    "value": str(len(result.findings)),
                    "inline": True,
                },
            ],
        }

    # -----------------------------------------------------------------
    async def code_test(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        code = (payload.get("code") or "").strip()
        if not code:
            raise SecuDeckError(
                "code 누락",
                user_message="테스트를 만들 코드를 함께 보내 주세요.",
            )
        language = (payload.get("language") or "").strip() or detect_language(code)
        result = await self.reviewer.generate_tests(
            code=_truncate(code),
            language=language,
            user_id=user_id,
        )
        return {
            "ok": True,
            "summary": result.text,
            "cost_krw": result.cost_krw,
            "blocks": [{"title": "언어", "value": language or "auto", "inline": True}],
        }

    # -----------------------------------------------------------------
    async def code_kisa(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        desc = (payload.get("feature_description") or "").strip()
        if not desc:
            raise SecuDeckError(
                "feature_description 누락",
                user_message="컴플라이언스 점검할 기능 설명을 함께 보내 주세요.",
            )
        # 너무 긴 설명은 자르기 (LLM 입력 한계 대비)
        if len(desc) > 6000:
            desc = desc[:6000] + "\n\n[설명 절단]"
        result = await self.reviewer.check_kisa(feature_description=desc, user_id=user_id)
        return {
            "ok": True,
            "summary": result.text,
            "cost_krw": result.cost_krw,
            "blocks": [{"title": "검사", "value": "KISA + 개인정보보호법", "inline": True}],
        }


__all__ = ["CodeInternalHandlers"]
