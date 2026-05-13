"""Chief of Staff 가 위임 호출하는 액션 핸들러 모음.

표준 응답 dict (sd_core.discord.internal_api 참조):
    {ok, summary, blocks, cost_krw, error}

라우팅에서 자주 들어올 액션:
- ``pitch_quick``: payload={"document_text": str} 또는
                   payload={"document_bytes": base64 str, "document_filename": str}
                   → 빠른 진단 (Sonnet 1회).
- ``pitch_focus``: payload 동일 + ``persona_id`` → 단일 페르소나.

PDF/DOCX 위임 처리:
- cos 가 의존성을 들이지 않으려고 PDF/DOCX 를 base64 bytes 로 그대로 넘긴다.
- 본 핸들러가 ``DocumentParser`` 의 정적 추출기를 호출해 텍스트로 변환한 뒤
  ReviewEngine 에 전달. 슬래시 커맨드 경로와 동일한 파서를 공유 → 결과 일관성 유지.

풀 리뷰(``pitch_review``)는 6 페르소나 병렬·1~2분 소요라 라우팅 응답에 부적합.
사용자가 직접 ``/pitch review`` 슬래시 커맨드를 쓰도록 둠.
"""
from __future__ import annotations

import base64
import binascii
from typing import Any

from sd_core.utils.errors import SecuDeckError

from pitch_sharpener.document_parser import DocumentParseError, DocumentParser
from pitch_sharpener.review_engine import ReviewEngine


class PitchInternalHandlers:
    """ReviewEngine 한 개 인스턴스를 공유해 슬래시 커맨드와 동일한 비용 추적."""

    def __init__(self, engine: ReviewEngine):
        self.engine = engine

    # -----------------------------------------------------------------
    async def pitch_quick(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        """1분 이내 빠른 진단."""
        document_text = self._resolve_document_text(payload)
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
        document_text = self._resolve_document_text(payload)
        persona_id = (payload.get("persona_id") or "").strip()
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


    # -----------------------------------------------------------------
    # 페이로드 → 사업계획서 본문 텍스트 결정 헬퍼.
    # cos delegator 가 보내는 두 가지 입력 형식을 모두 처리.
    # -----------------------------------------------------------------
    @staticmethod
    def _resolve_document_text(payload: dict[str, Any]) -> str:
        """payload 에서 document_text 를 얻는다.

        우선순위:
        1) ``document_text`` 키가 비어 있지 않으면 그대로 사용 (텍스트 직접 전달).
        2) ``document_bytes`` (base64) + ``document_filename`` 으로 PDF/DOCX 파싱.
        둘 다 없거나 파싱 실패 시 ``SecuDeckError`` — cos 가 사용자에게 안내 임베드를 표시.
        """
        text = (payload.get("document_text") or "").strip()
        if text:
            return text

        encoded = payload.get("document_bytes")
        if not encoded:
            raise SecuDeckError(
                "document_text / document_bytes 모두 누락",
                user_message=(
                    "진단할 사업계획서 본문이 비어 있어요. "
                    "본문 텍스트나 PDF/DOCX/MD/TXT 파일을 함께 보내 주세요."
                ),
            )

        # base64 디코딩 — 형식 오류는 사용자 친화 메시지로 변환.
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise SecuDeckError(
                f"document_bytes base64 디코딩 실패: {exc}",
                user_message="첨부 파일을 읽는 중 오류가 발생했어요. 파일을 다시 보내 주세요.",
            ) from exc

        filename = (payload.get("document_filename") or "").lower()
        try:
            if filename.endswith(".pdf"):
                return DocumentParser._extract_pdf(raw)
            if filename.endswith(".docx"):
                return DocumentParser._extract_docx(raw)
            # 확장자 모를 때는 UTF-8 텍스트로 시도 (대부분 .md/.txt 가 여기 옴).
            try:
                fallback = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise DocumentParseError(
                    "지원하지 않는 형식이에요. PDF, DOCX, MD, TXT 만 가능합니다."
                ) from exc
            if not fallback.strip():
                raise DocumentParseError("문서에서 텍스트를 추출하지 못했어요.")
            return fallback
        except DocumentParseError as exc:
            # DocumentParser 가 던지는 사용자 친화 메시지를 그대로 노출.
            raise SecuDeckError(str(exc), user_message=str(exc)) from exc


__all__ = ["PitchInternalHandlers"]
