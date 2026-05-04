"""의도 분류 — 사용자 자연어 + 첨부파일 → (봇, 액션, 파라미터).

전략 2단계:
1. **룰베이스 1차** (무비용): 첨부 확장자 + 강력한 키워드. 명확하면 바로 결정.
2. **LLM 2차** (Haiku, 약 30원): 룰로 안 잡힌 자연어. JSON 강제 출력.

JSON 파싱은 ``_safe_json_parse`` 로 코드블록 제거 + ``{ ... }`` 추출 폴백 (CLAUDE.md 함정 ²).

bot/action 카탈로그는 4개 봇의 ``internal_handlers.py`` 와 동기화 유지.
새 액션 추가 시 ``ROUTABLE_ACTIONS`` + LLM 시스템 프롬프트의 카탈로그도 갱신할 것.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, TaskType
from sd_core.utils.logger import get_logger


_log = get_logger("chief_of_staff.intent_router")


@dataclass
class Intent:
    """분류 결과. ``bot == 'self'`` 면 cos 가 직접 답변."""

    bot: str
    action: str
    reason: str = ""
    confidence: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)
    source: str = "llm"   # "rule" | "llm" | "fallback"


# ---------------------------------------------------------------------
# 라우팅 가능한 (bot, action) 카탈로그 — 봇별 internal_handlers.py 와 동기화 필수.
# 값은 LLM 시스템 프롬프트에 그대로 주입되어 1줄 설명 역할.
# ---------------------------------------------------------------------
ROUTABLE_ACTIONS: dict[tuple[str, str], str] = {
    ("pitch_sharpener", "pitch_quick"):
        "사업계획서 본문 1~2분 빠른 진단. 6대 1차 탈락 원인 충족도 평가.",
    ("pitch_sharpener", "pitch_focus"):
        "사업계획서 단일 페르소나 깊이 리뷰. params.persona_id 권장 (customer_voice / data_skeptic / pricing_analyst / competitor_hunter / tech_differentiator / budget_reality).",
    ("code_sentinel", "code_review"):
        "코드 리뷰. params.language(자동감지 가능), params.focus='security'면 보안 중심.",
    ("code_sentinel", "code_test"):
        "코드의 단위 테스트 자동 생성.",
    ("code_sentinel", "code_kisa"):
        "신규 기능 설명 → KISA·개인정보보호법 정합성 점검. params.feature_description 필수.",
    ("interview_companion", "interview_prep"):
        "고객 인터뷰 가이드 생성. params={name, role, company, company_size, background?, focus_ids?} 필요.",
    ("interview_companion", "interview_insight"):
        "누적 인터뷰 분석 (페인·인용구·가설 검증).",
    ("design_echo", "design_check"):
        "디자인 시안(이미지) DS 일관성 검사 + 톤 검사.",
    ("design_echo", "design_spec"):
        "디자인 시안(이미지) → 개발 핸드오프 spec. params.screen_name 필수.",
    ("design_echo", "design_copy"):
        "UX 카피 검토. params={current_copy, screen_context?, purpose?}.",
    ("self", "answer"):
        "위 봇으로 위임할 필요가 없는 가벼운 일반 질문. cos 가 직접 답변.",
}


# ---------------------------------------------------------------------
# 룰베이스 1차 — 첨부 확장자 + 명확한 키워드만. 애매하면 LLM 으로.
# ---------------------------------------------------------------------
_CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb",
              ".php", ".cs", ".cpp", ".c", ".h", ".swift", ".sql"}
_PITCH_DOC_EXTS = {".pdf", ".docx", ".md", ".txt"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

_KISA_HINTS = re.compile(r"(KISA|개인정보보호법|PIPA|컴플라이언스|위탁자)", re.IGNORECASE)
_PITCH_HINTS = re.compile(r"(사업계획서|피치|지원사업|투자|IR|deck)", re.IGNORECASE)
_INTERVIEW_HINTS = re.compile(r"(인터뷰|고객.*페인|누적.*분석|고객 인사이트)", re.IGNORECASE)
_COPY_HINTS = re.compile(r"(카피|문구|버튼.*텍스트|CTA|마이크로카피|문장.*톤)", re.IGNORECASE)
_DESIGN_SPEC_HINTS = re.compile(r"(spec|핸드오프|개발자에게|토큰.*추출)", re.IGNORECASE)
_SECURITY_HINTS = re.compile(r"(보안|취약|injection|XSS|CSRF|PII|민감.*정보)", re.IGNORECASE)


@dataclass
class RouteInput:
    """디스코드 메시지에서 router 가 보는 정보 (디스코드 객체 의존 제거)."""

    text: str
    attachment_filenames: list[str] = field(default_factory=list)
    attachment_content_types: list[str] = field(default_factory=list)


class IntentRouter:
    """룰 + LLM 2단계 의도 분류."""

    def __init__(self, llm: LLMRouter, *, bot_name: str = "chief_of_staff"):
        self.llm = llm
        self.bot_name = bot_name
        self._system_prompt = self._build_system_prompt()

    # -----------------------------------------------------------------
    async def classify(self, route_in: RouteInput, user_id: str) -> Intent:
        """입력 → Intent. 실패 시 ``Intent(bot='self', action='answer', source='fallback')``."""
        # 1) 룰베이스 시도
        rule = self._classify_by_rules(route_in)
        if rule is not None:
            _log.info(
                "intent_rule",
                bot=rule.bot,
                action=rule.action,
                reason=rule.reason,
            )
            return rule

        # 2) LLM 분류
        try:
            return await self._classify_by_llm(route_in, user_id)
        except Exception as exc:  # noqa: BLE001
            _log.warning("intent_llm_failed", error=str(exc))
            # 폴백: cos 가 직접 답변 시도
            return Intent(
                bot="self",
                action="answer",
                reason=f"의도 분류 실패 ({exc.__class__.__name__})",
                confidence=0.0,
                source="fallback",
            )

    # -----------------------------------------------------------------
    # 룰베이스
    # -----------------------------------------------------------------
    def _classify_by_rules(self, route_in: RouteInput) -> Intent | None:
        text = route_in.text or ""
        names = [n.lower() for n in route_in.attachment_filenames]
        types = [t.lower() for t in route_in.attachment_content_types]

        def has_ext(exts: set[str]) -> bool:
            return any(any(n.endswith(e) for e in exts) for n in names)

        def has_image() -> bool:
            if has_ext(_IMAGE_EXTS):
                return True
            return any(t.startswith("image/") for t in types)

        # 명시적 KISA/컴플라이언스
        if _KISA_HINTS.search(text) and not (has_ext(_CODE_EXTS) or has_image()):
            return Intent(
                bot="code_sentinel",
                action="code_kisa",
                reason="KISA/PIPA 키워드 + 코드 첨부 없음",
                confidence=0.85,
                params={"feature_description": text},
                source="rule",
            )

        # 코드 파일 첨부 → code_review (보안 키워드 있으면 focus=security)
        if has_ext(_CODE_EXTS):
            params: dict[str, Any] = {}
            if _SECURITY_HINTS.search(text):
                params["focus"] = "security"
            return Intent(
                bot="code_sentinel",
                action="code_review",
                reason="코드 파일 첨부",
                confidence=0.8,
                params=params,
                source="rule",
            )

        # 사업계획서 문서 (PDF/DOCX/MD/TXT) 첨부
        if has_ext(_PITCH_DOC_EXTS):
            return Intent(
                bot="pitch_sharpener",
                action="pitch_quick",  # 라우팅에선 quick 이 안전 (focus 는 LLM 분류로)
                reason="문서(PDF/DOCX/MD) 첨부",
                confidence=0.6,
                source="rule",
            )

        # 이미지 첨부 — spec 키워드면 design_spec, 아니면 design_check
        if has_image():
            if _DESIGN_SPEC_HINTS.search(text) or "spec" in text.lower() or "스펙" in text:
                return Intent(
                    bot="design_echo",
                    action="design_spec",
                    reason="이미지 + spec 키워드",
                    confidence=0.75,
                    source="rule",
                )
            if _COPY_HINTS.search(text):
                # 이미지 + 카피 키워드 — design_copy 는 이미지가 없어도 동작하므로 LLM 으로 위임
                return None
            return Intent(
                bot="design_echo",
                action="design_check",
                reason="이미지 첨부",
                confidence=0.7,
                source="rule",
            )

        # 강한 인터뷰 키워드
        if _INTERVIEW_HINTS.search(text):
            # 가이드 vs 누적분석 구분은 LLM 으로 — 입력 정보가 부족할 때 명확치 않음.
            return None

        # 강한 사업계획서 키워드 (첨부 없는 경우)
        if _PITCH_HINTS.search(text):
            # 본문 텍스트가 충분히 길면 quick, 아니면 self (cos 안내)
            return None

        return None

    # -----------------------------------------------------------------
    # LLM 분류
    # -----------------------------------------------------------------
    async def _classify_by_llm(self, route_in: RouteInput, user_id: str) -> Intent:
        # user 메시지에 첨부 메타데이터를 텍스트로 노출 (Haiku 가 룰 못 잡은 경우 보강).
        atts_desc = self._summarize_attachments(route_in)
        user_text = (
            f"## 사용자 메시지\n{route_in.text or '(빈 메시지)'}\n\n"
            f"## 첨부\n{atts_desc or '(없음)'}\n"
        )

        request = LLMRequest(
            task_type=TaskType.ROUTING,
            system=self._system_prompt,
            messages=[{"role": "user", "content": user_text}],
            user_id=user_id,
            bot_name=self.bot_name,
            max_tokens=300,
            temperature=0.0,
        )
        response = await self.llm.call(request)
        parsed = _safe_json_parse(response.text)
        if not isinstance(parsed, dict):
            _log.warning("intent_llm_unparseable", text=response.text[:200])
            return Intent(
                bot="self",
                action="answer",
                reason="LLM 응답 JSON 파싱 실패",
                confidence=0.0,
                source="fallback",
            )

        bot = str(parsed.get("bot") or "self")
        action = str(parsed.get("action") or "answer")
        if (bot, action) not in ROUTABLE_ACTIONS:
            _log.warning("intent_llm_unknown_target", bot=bot, action=action)
            return Intent(
                bot="self",
                action="answer",
                reason=f"LLM 이 알 수 없는 target 반환: {bot}/{action}",
                confidence=0.0,
                source="fallback",
            )

        params_raw = parsed.get("params") or {}
        if not isinstance(params_raw, dict):
            params_raw = {}

        # confidence 안전 변환
        try:
            conf = float(parsed.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0

        return Intent(
            bot=bot,
            action=action,
            reason=str(parsed.get("reason") or ""),
            confidence=max(0.0, min(1.0, conf)),
            params=params_raw,
            source="llm",
        )

    # -----------------------------------------------------------------
    @staticmethod
    def _summarize_attachments(route_in: RouteInput) -> str:
        if not route_in.attachment_filenames:
            return ""
        items: list[str] = []
        for i, name in enumerate(route_in.attachment_filenames):
            ctype = route_in.attachment_content_types[i] if i < len(route_in.attachment_content_types) else ""
            items.append(f"- {name} ({ctype or '?'})")
        return "\n".join(items)

    # -----------------------------------------------------------------
    # 시스템 프롬프트 — Argos 컨텍스트는 의도 분류에 불필요하므로 제외 (캐시는 카탈로그로 확보).
    # -----------------------------------------------------------------
    @staticmethod
    def _build_system_prompt() -> str:
        catalog_lines = ["# 라우팅 카탈로그 (정확히 이 (bot, action) 조합만 사용)"]
        for (bot, action), desc in ROUTABLE_ACTIONS.items():
            catalog_lines.append(f"- bot=`{bot}`, action=`{action}` — {desc}")

        return "\n".join([
            "당신은 Secu Deck 의 'Chief of Staff' 봇의 의도 분류기입니다.",
            "사용자의 자연어 메시지와 첨부 메타데이터를 보고, 어떤 봇의 어떤 액션으로 위임할지 결정합니다.",
            "",
            "## 출력 규약",
            "JSON 객체 1개만 출력하세요. 코드블록·설명·prefix 금지.",
            "스키마:",
            '{"bot": "<카탈로그의 bot>", "action": "<카탈로그의 action>", '
            '"params": {<필요 시 핵심 파라미터>}, '
            '"reason": "<짧은 한국어 1문장>", "confidence": <0.0~1.0>}',
            "",
            "## 결정 가이드",
            "- 위임 가치가 낮은 인사·잡담·메타 질문(이 봇 뭐임? 등) → bot='self', action='answer'.",
            "- 사용자 메시지에 페르소나·가설 ID 등이 명시돼 있으면 params 에 그대로 옮겨 담을 것.",
            "- 정보가 부족해 위임이 어려우면 self 로 보내 cos 가 추가 정보를 요청하도록.",
            "- 절대 카탈로그에 없는 (bot, action) 을 만들지 말 것.",
            "",
            *catalog_lines,
        ])


# ---------------------------------------------------------------------
# JSON 파서 — Sonnet/Haiku 가 가끔 ```json 으로 감싸거나 prefix 를 붙이는 경우 대비.
# CLAUDE.md 의 ``interview_logger._safe_json_parse`` 패턴과 동일.
# ---------------------------------------------------------------------
_CODEBLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _safe_json_parse(text: str) -> Any:
    """1) 코드블록 제거 → 2) 직파싱 → 3) ``{ ... }`` 추출 폴백."""
    if not text:
        return None
    candidate = text.strip()

    m = _CODEBLOCK_RE.search(candidate)
    if m:
        candidate = m.group(1).strip()

    try:
        return json.loads(candidate)
    except (ValueError, TypeError):
        pass

    # 폴백: 첫 { ~ 마지막 } 사이만 시도
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except (ValueError, TypeError):
            return None
    return None


__all__ = ["IntentRouter", "Intent", "RouteInput", "ROUTABLE_ACTIONS"]
