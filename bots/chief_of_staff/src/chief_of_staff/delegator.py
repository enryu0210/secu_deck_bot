"""봇 위임 호출 — Intent + 디스코드 메시지 → 봇 internal API invoke 페이로드 구성.

책임:
- 첨부파일 다운로드 (Attachment.read) + 컨텐츠 타입별 인코딩 (텍스트 디코딩 / base64).
- IntentRouter 가 채운 ``params`` 를 봇 internal_handlers 가 기대하는 키로 보강.
- ``InternalAPIClient.invoke`` 호출 후 결과 dict 반환.

PDF/DOCX 파싱 정책:
- cos 자체에는 pypdf / python-docx 의존성을 두지 않는다 (의존성 폭발 회피).
- 대신 첨부 bytes 를 base64 로 인코딩해 위임 봇(pitch_sharpener)에 그대로 넘기고,
  파싱은 pitch 봇이 이미 보유한 ``DocumentParser`` 에 맡긴다.
- 이렇게 하면 사용자는 @cos 멘션에 PDF 를 그대로 던질 수 있으면서도 cos 컨테이너의
  의존성은 가볍게 유지된다.
"""
from __future__ import annotations

import base64
from typing import Any

import discord

from sd_core.discord.internal_client import InternalAPIClient
from sd_core.utils.errors import SecuDeckError
from sd_core.utils.logger import get_logger

from chief_of_staff.intent_router import Intent


_log = get_logger("chief_of_staff.delegator")


# 텍스트 디코딩 시 시도할 인코딩 (한국어 문서 자주 cp949 / euc-kr).
_TEXT_DECODE_CANDIDATES = ("utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1")
_CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb",
              ".php", ".cs", ".cpp", ".c", ".h", ".swift", ".sql"}
_TEXT_EXTS = {".md", ".txt"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_BINARY_DOC_EXTS = {".pdf", ".docx"}

# 텍스트 첨부 최대 크기 (디스코드 일반 첨부 8MB 한계 대비 LLM 입력에 안전한 600KB)
_MAX_TEXT_BYTES = 600 * 1024
# 바이너리 문서(PDF/DOCX) 위임 시 base64 직전 원본 크기 상한.
# pitch 봇의 DocumentParser._MAX_ATTACHMENT_BYTES 와 맞춰서 결정 — 20MB.
_MAX_DOC_BYTES = 20 * 1024 * 1024


class Delegator:
    """Intent → 봇 invoke 호출."""

    def __init__(self, client: InternalAPIClient):
        self.client = client

    async def execute(
        self,
        intent: Intent,
        message: discord.Message,
        user_id: str,
    ) -> dict[str, Any]:
        """위임 실행. 표준 응답 dict 반환."""
        if intent.bot == "self":
            # self 의도는 Synthesizer 에서 처리 — Delegator 가 호출되면 안 됨.
            raise SecuDeckError(
                "Delegator 가 self 의도로 호출됨",
                user_message="내부 라우팅 오류가 발생했어요.",
            )

        payload = await self._build_payload(intent, message)
        # schedule_bot 은 모든 액션이 guild_id 필요 — cos 가 디스코드 컨텍스트에서 자동 주입.
        # (사용자는 DM 에서 쓰면 안 되며, 그 경우 핸들러가 친절 에러를 반환한다.)
        if intent.bot == "schedule_bot":
            self._inject_guild_context(payload, message)
        _log.info(
            "delegate_invoke",
            bot=intent.bot,
            action=intent.action,
            payload_keys=sorted(payload.keys()),
            confidence=intent.confidence,
        )
        return await self.client.invoke(
            bot=intent.bot,
            action=intent.action,
            payload=payload,
            user_id=user_id,
        )

    # -----------------------------------------------------------------
    # 페이로드 빌더 — action 별로 필요한 키를 보강.
    # -----------------------------------------------------------------
    async def _build_payload(
        self,
        intent: Intent,
        message: discord.Message,
    ) -> dict[str, Any]:
        # IntentRouter 가 미리 채운 params 를 base 로 시작.
        payload: dict[str, Any] = dict(intent.params or {})
        action = intent.action
        text = message.content or ""
        # 디스코드는 봇 멘션이 ``<@id>`` 로 들어옴 → 제거해 봇 입력 정리.
        clean_text = _strip_bot_mention(text, message.guild and message.guild.me).strip()

        if action in ("pitch_quick", "pitch_focus"):
            await self._fill_document_text(payload, message, clean_text)
            return payload

        if action in ("code_review", "code_test"):
            await self._fill_code(payload, message, clean_text)
            return payload

        if action == "code_kisa":
            payload.setdefault("feature_description", clean_text)
            if not payload.get("feature_description"):
                raise SecuDeckError(
                    "feature_description 비어 있음",
                    user_message="컴플라이언스 점검할 기능 설명을 함께 보내 주세요.",
                )
            return payload

        if action == "interview_prep":
            # IntentRouter LLM 이 name/role/company/company_size 를 파라미터로 채워야 정상.
            # 비어 있으면 사용자에게 보충 요청.
            required = ("name", "role", "company", "company_size")
            missing = [k for k in required if not payload.get(k)]
            if missing:
                raise SecuDeckError(
                    f"interview_prep 누락 필드: {missing}",
                    user_message=(
                        "인터뷰 가이드를 만들려면 인터뷰이의 이름·역할·회사·회사 규모가 필요해요. "
                        "예: '대표 A, CISO, 웰컴저축은행, 200인 이하' 형태로 알려주세요."
                    ),
                )
            return payload

        if action == "interview_insight":
            # 별도 페이로드 불필요 — user_id 만으로 분석.
            return payload

        if action in ("design_check", "design_spec"):
            await self._fill_image_b64(payload, message)
            if action == "design_spec":
                # screen_name 우선순위: params → message 본문.
                payload.setdefault("screen_name", clean_text or "(이름 없음)")
            return payload

        if action == "design_copy":
            payload.setdefault("current_copy", clean_text)
            if not payload.get("current_copy"):
                raise SecuDeckError(
                    "current_copy 비어 있음",
                    user_message="검토할 카피 원문을 함께 보내 주세요.",
                )
            return payload

        if action == "audit_scan":
            # 별도 페이로드 불필요 — 봇이 ARGOS_REPO_URL 기준으로 스캔.
            return payload

        if action == "audit_feature":
            # PRD 텍스트는 첨부 .md/.txt 도 허용. 첨부 없으면 메시지 본문 사용.
            await self._fill_document_text(payload, message, clean_text)
            # _fill_document_text 는 document_text 키에 채우므로 prd_text 로 옮김.
            if "prd_text" not in payload and "document_text" in payload:
                payload["prd_text"] = payload.pop("document_text")
            if not payload.get("prd_text"):
                raise SecuDeckError(
                    "prd_text 비어 있음",
                    user_message="법령 매핑할 PRD 본문을 메시지로 보내거나 .md/.txt 파일을 첨부해 주세요.",
                )
            return payload

        # ─────────────────── schedule_bot ───────────────────
        # 조회 4종 — params 별도 필요 없음 (search 만 date 필수, IntentRouter LLM/룰이 채움).
        if action in ("schedule_today", "schedule_week", "schedule_upcoming"):
            return payload

        if action == "schedule_search":
            if not payload.get("date"):
                raise SecuDeckError(
                    "schedule_search date 누락",
                    user_message="조회할 날짜를 알려주세요. 예: `2026-04-15` 또는 `4월 15일`.",
                )
            return payload

        if action == "schedule_register":
            # title/date 필수. time/description 선택. created_by 는 디스코드 사용자명으로 자동 주입.
            missing = [k for k in ("title", "date") if not payload.get(k)]
            if missing:
                raise SecuDeckError(
                    f"schedule_register 누락 필드: {missing}",
                    user_message=(
                        "일정을 등록하려면 제목과 날짜가 필요해요. "
                        "예: '내일 14시 팀 회의 등록해줘' (날짜·시간 명시) 형태로 알려주세요."
                    ),
                )
            payload.setdefault("created_by", str(message.author))
            return payload

        # 알 수 없는 action — IntentRouter 카탈로그와 동기화 누락 가능.
        raise SecuDeckError(
            f"Delegator 가 모르는 action: {action}",
            user_message="내부 라우팅이 처리할 수 없는 작업이에요.",
        )

    # -----------------------------------------------------------------
    # guild_id 자동 주입 — schedule_bot 전용. 사용자가 매번 명시할 필요 없게.
    # -----------------------------------------------------------------
    @staticmethod
    def _inject_guild_context(payload: dict[str, Any], message: discord.Message) -> None:
        """디스코드 메시지에서 guild_id 를 끌어와 payload 에 강제 주입.

        DM(메시지의 guild 가 None) 일 때 굳이 ConfigError 던지지 않고 빈 값을 둔다 —
        schedule_bot 핸들러가 친절한 한국어 에러로 처리하도록 책임 위임.
        """
        if message.guild is not None:
            payload["guild_id"] = str(message.guild.id)

    # -----------------------------------------------------------------
    # 첨부 헬퍼
    # -----------------------------------------------------------------
    @staticmethod
    async def _fill_document_text(
        payload: dict[str, Any],
        message: discord.Message,
        fallback_text: str,
    ) -> None:
        """문서 첨부 → document_text 또는 document_bytes.

        우선순위:
        1) payload 에 이미 document_text 가 있으면 그대로 사용 (LLM 분류 결과 보존).
        2) 첨부에 .md/.txt 가 있으면 즉시 디코딩해 document_text 로 세팅.
        3) 첨부에 .pdf/.docx 가 있으면 bytes 를 base64 로 인코딩해 document_bytes 로 전달.
           파싱은 위임 봇(pitch_sharpener) 의 DocumentParser 가 담당.
        4) 모두 없으면 메시지 본문(fallback_text) 을 document_text 로 사용.
        """
        if payload.get("document_text"):
            return

        # 1순위 — 텍스트 파일은 그 자리에서 디코딩 (LLM 입력 토큰 절약 + 단순).
        for att in message.attachments:
            name = (att.filename or "").lower()
            if any(name.endswith(ext) for ext in _TEXT_EXTS):
                raw = await att.read()
                payload["document_text"] = _decode_text(raw)
                return

        # 2순위 — PDF/DOCX 는 bytes 그대로 위임. cos 에 pypdf/docx 의존성 없음.
        for att in message.attachments:
            name = (att.filename or "").lower()
            if any(name.endswith(ext) for ext in _BINARY_DOC_EXTS):
                if att.size > _MAX_DOC_BYTES:
                    raise SecuDeckError(
                        f"문서 첨부가 너무 큼: {att.size} bytes",
                        user_message="문서가 너무 커요 (20MB 이하만 지원). 본문만 추출해 다시 보내 주세요.",
                    )
                raw = await att.read()
                payload["document_bytes"] = base64.b64encode(raw).decode("ascii")
                # 위임 봇이 확장자로 파서를 고를 수 있도록 파일명도 함께 전달.
                payload["document_filename"] = att.filename or name
                return

        # 3순위 — 첨부에 텍스트/문서 둘 다 없으면 메시지 본문 사용.
        if not fallback_text:
            raise SecuDeckError(
                "document_text 와 첨부 모두 없음",
                user_message=(
                    "진단할 사업계획서 본문을 메시지로 보내거나 PDF/DOCX/MD/TXT 파일을 첨부해 주세요."
                ),
            )
        payload["document_text"] = fallback_text

    @staticmethod
    async def _fill_code(
        payload: dict[str, Any],
        message: discord.Message,
        fallback_text: str,
    ) -> None:
        """코드 첨부 → code. 첨부 없으면 메시지 본문(``-coded fence`` 포함 가능)을 사용."""
        if payload.get("code"):
            return

        # 코드 확장자 우선
        for att in message.attachments:
            name = (att.filename or "").lower()
            if any(name.endswith(ext) for ext in _CODE_EXTS):
                raw = await att.read()
                payload["code"] = _decode_text(raw)
                # 언어 추정 (params 가 비어 있을 때만)
                payload.setdefault("language", name.rsplit(".", 1)[-1])
                return

        # 일반 텍스트 파일도 허용
        for att in message.attachments:
            name = (att.filename or "").lower()
            if any(name.endswith(ext) for ext in _TEXT_EXTS):
                raw = await att.read()
                payload["code"] = _decode_text(raw)
                return

        if not fallback_text:
            raise SecuDeckError(
                "code 누락",
                user_message="리뷰할 코드를 첨부하거나 메시지에 직접 붙여 주세요.",
            )
        payload["code"] = fallback_text

    @staticmethod
    async def _fill_image_b64(
        payload: dict[str, Any],
        message: discord.Message,
    ) -> None:
        if payload.get("image_b64"):
            return
        for att in message.attachments:
            name = (att.filename or "").lower()
            ctype = (att.content_type or "").lower()
            if any(name.endswith(ext) for ext in _IMAGE_EXTS) or ctype.startswith("image/"):
                raw = await att.read()
                payload["image_b64"] = base64.b64encode(raw).decode("ascii")
                return
        raise SecuDeckError(
            "이미지 첨부 없음",
            user_message="검사할 시안 이미지를 첨부해 주세요. (PNG/JPG)",
        )


# ---------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------
def _strip_bot_mention(text: str, bot_member) -> str:
    """``<@bot_id>`` 와 ``<@!bot_id>`` 멘션을 제거."""
    if not bot_member:
        return text
    bot_id = bot_member.id
    return text.replace(f"<@{bot_id}>", "").replace(f"<@!{bot_id}>", "")


def _decode_text(raw: bytes) -> str:
    """여러 인코딩으로 시도. 모두 실패하면 latin-1 로 강제 (정보 손실 없이 1:1)."""
    if len(raw) > _MAX_TEXT_BYTES:
        raw = raw[:_MAX_TEXT_BYTES]
    for enc in _TEXT_DECODE_CANDIDATES:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


__all__ = ["Delegator"]
