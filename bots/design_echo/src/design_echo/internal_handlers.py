"""Chief of Staff 위임용 액션 핸들러.

지원 액션:
- ``design_check``: payload={"image_b64": str} → DS 일관성 검사
- ``design_spec``:  payload={"image_b64": str, "screen_name": str}
- ``design_copy``:  payload={"screen_context": str, "purpose": str, "current_copy": str}

이미지는 base64 인코딩 문자열로 받음 — JSON body 안전 전송.
"""
from __future__ import annotations

import base64
import binascii
from typing import Any

from sd_core.utils.errors import SecuDeckError

from design_echo.consistency_checker import ConsistencyChecker
from design_echo.copy_reviewer import CopyReviewer
from design_echo.spec_generator import SpecGenerator


# 디스코드 첨부 8MB 제한 + base64 ~33% overhead → 입력 base64 ~10MB 까지 허용.
_MAX_IMAGE_B64 = 10 * 1024 * 1024


def _decode_image(b64: str) -> bytes:
    """base64 디코드 + 길이/형식 방어."""
    if not b64:
        raise SecuDeckError(
            "image_b64 누락",
            user_message="검사할 시안 이미지를 첨부해 주세요.",
        )
    if len(b64) > _MAX_IMAGE_B64:
        raise SecuDeckError(
            "이미지 base64 길이 초과",
            user_message="이미지가 너무 커요. 8MB 이하 PNG/JPG 로 다시 보내 주세요.",
        )
    # data URL prefix 제거 ("data:image/png;base64,...")
    if b64.startswith("data:"):
        comma = b64.find(",")
        if comma > 0:
            b64 = b64[comma + 1 :]
    try:
        return base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SecuDeckError(
            f"base64 디코드 실패: {exc}",
            user_message="이미지 파일이 손상됐거나 base64 인코딩이 잘못됐어요.",
        ) from exc


class DesignInternalHandlers:
    def __init__(
        self,
        checker: ConsistencyChecker,
        spec: SpecGenerator,
        copy: CopyReviewer,
    ):
        self.checker = checker
        self.spec = spec
        self.copy = copy

    # -----------------------------------------------------------------
    async def design_check(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        image_bytes = _decode_image(str(payload.get("image_b64") or ""))
        result = await self.checker.check(image_bytes=image_bytes, user_id=user_id)

        # CheckSummary.diffs (TokenDiff 리스트) 를 severity 별로 카운트.
        diffs = result.summary.diffs
        errors = [d for d in diffs if d.severity == "error"]
        warns = [d for d in diffs if d.severity == "warn"]

        lines: list[str] = ["## DS 일관성 검사 결과"]
        lines.append(f"- 에러 {len(errors)} · 경고 {len(warns)} · 톤 이슈 {len(result.tone_issues)}")

        # 가장 시급한 에러 3건 미리보기 (cos 답글에 그대로 노출 가능 길이)
        if errors:
            lines.append("\n### 주요 에러")
            for d in errors[:3]:
                lines.append(f"- [{d.kind}] {d.message}")
        elif warns:
            lines.append("\n### 주요 경고")
            for d in warns[:3]:
                lines.append(f"- [{d.kind}] {d.message}")

        if result.tone_issues:
            lines.append("\n### 톤 이슈 (최대 3건)")
            for issue in result.tone_issues[:3]:
                lines.append(f"- '{issue.text[:60]}' → {issue.suggestion[:80]}")

        if result.parse_warning:
            lines.append(f"\n⚠️ {result.parse_warning}")

        return {
            "ok": True,
            "summary": "\n".join(lines),
            "cost_krw": result.cost_krw,
            "blocks": [
                {"title": "에러", "value": str(len(errors)), "inline": True},
                {"title": "경고", "value": str(len(warns)), "inline": True},
                {"title": "톤 이슈", "value": str(len(result.tone_issues)), "inline": True},
            ],
        }

    # -----------------------------------------------------------------
    async def design_spec(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        image_bytes = _decode_image(str(payload.get("image_b64") or ""))
        screen_name = str(payload.get("screen_name") or "").strip()
        if not screen_name:
            raise SecuDeckError(
                "screen_name 누락",
                user_message="화면 이름을 함께 알려주세요. 예: '대시보드 홈'.",
            )
        spec = await self.spec.generate(
            image_bytes=image_bytes,
            screen_name=screen_name,
            user_id=user_id,
        )
        return {
            "ok": True,
            "summary": spec.text,
            "cost_krw": spec.cost_krw,
            "blocks": [{"title": "화면", "value": screen_name, "inline": True}],
        }

    # -----------------------------------------------------------------
    async def design_copy(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        screen_context = str(payload.get("screen_context") or "")
        purpose = str(payload.get("purpose") or "")
        current_copy = str(payload.get("current_copy") or "")
        if not current_copy.strip():
            raise SecuDeckError(
                "current_copy 누락",
                user_message="검토할 카피 원문을 함께 보내 주세요.",
            )
        review = await self.copy.review(
            screen_context=screen_context,
            purpose=purpose,
            current_copy=current_copy,
            user_id=user_id,
        )
        return {
            "ok": True,
            "summary": review.text,
            "cost_krw": review.cost_krw,
            "blocks": [
                {"title": "원문", "value": current_copy[:200], "inline": False},
            ],
        }


__all__ = ["DesignInternalHandlers"]
