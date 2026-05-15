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
        "코드 본문(텍스트/첨부) 리뷰. params.language(자동감지 가능), params.focus='security'면 보안 중심. 브랜치 단위가 아닐 때만.",
    ("code_sentinel", "code_test"):
        "코드의 단위 테스트 자동 생성.",
    ("code_sentinel", "code_kisa"):
        "신규 기능 설명 → KISA·개인정보보호법 정합성 점검. params.feature_description 필수.",
    ("code_sentinel", "code_branch_diff"):
        "GitHub 브랜치 ↔ base diff 리뷰 — 사용자가 '변경된 부분/diff/main 대비/달라진' 같이 '차이'를 강조할 때. params.branch 필수, params.repo·params.base 선택.",
    ("code_sentinel", "code_branch_snapshot"):
        "GitHub 브랜치 전체 코드 통째 리뷰 — 사용자가 '전체/통째/모든 파일/스냅샷' 같이 '브랜치 자체'를 강조할 때만 (비용 큼). params.branch 필수, params.repo 선택.",
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
    ("argos_self_audit", "audit_scan"):
        "Argos 레포 즉시 룰베이스 스캔 (시크릿/PII/KISA/레거시 + 의존성 CVE). LLM 호출 없음.",
    ("argos_self_audit", "audit_feature"):
        "신규 기능 PRD 텍스트 → 개인정보보호법 조항 키워드 매핑 + 위험 시나리오. params.prd_text 필수. LLM 호출 없음.",
    ("schedule_bot", "schedule_today"):
        "오늘 등록된 팀 일정 목록. payload 자동 (guild_id 는 cos 가 주입).",
    ("schedule_bot", "schedule_week"):
        "이번 주(오늘~일요일) 일정 목록.",
    ("schedule_bot", "schedule_upcoming"):
        "다가오는 일정 최대 10건. '다음 일정', '예정된 일정' 같은 질문에 사용.",
    ("schedule_bot", "schedule_search"):
        "특정 날짜 일정. params.date='YYYY-MM-DD' 필수. '4월 15일 일정' 같이 날짜가 명시될 때.",
    ("schedule_bot", "schedule_register"):
        "팀 일정 등록. params={title, date(YYYY-MM-DD), time?(HH:MM), description?} 필수.",
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

# ---------------------------------------------------------------------
# 브랜치 리뷰 트리거 — diff vs snapshot 을 명확히 분리.
# 같은 메시지에 두 신호가 모두 잡히면 SNAPSHOT 이 더 명시적 표현이므로 우선.
# 그 외엔 DIFF 가 안전·저비용 기본값.
# ---------------------------------------------------------------------
# "브랜치/branch 또는 흔한 브랜치 prefix" — 브랜치 의도 자체를 잡는 1차 신호.
_BRANCH_HINTS = re.compile(
    r"(브랜치|branch|feature/[\w\-./]+|hotfix/[\w\-./]+|bugfix/[\w\-./]+|fix/[\w\-./]+|release/[\w\-./]+|exp/[\w\-./]+)",
    re.IGNORECASE,
)
# 명시적 브랜치명 캡처 — prefix-style 만 (자유형 브랜치명은 LLM 으로 위임).
_BRANCH_NAME_RE = re.compile(
    r"(feature/[\w\-./]+|hotfix/[\w\-./]+|bugfix/[\w\-./]+|fix/[\w\-./]+|release/[\w\-./]+|exp/[\w\-./]+)",
)
# "전체/통째/모든 파일/스냅샷" — 스냅샷 강한 키워드.
_BRANCH_FULL_HINTS = re.compile(
    r"(브랜치\s*전체|전체\s*리뷰|통째|모든\s*파일|스냅샷|snapshot|full\s*review|whole\s*branch)",
    re.IGNORECASE,
)
# "변경/diff/차이/main 대비/달라진" — diff 강한 키워드.
_BRANCH_DIFF_HINTS = re.compile(
    r"(변경.?사항|차이.?점|diff|main\s*대비|base\s*대비|PR\s*전|미리\s*리뷰|"
    r"어떻게\s*바뀌|뭐가\s*달라|달라진\s*점|어떤\s*변경)",
    re.IGNORECASE,
)
# self-audit 즉시 스캔을 명시적으로 부르는 키워드 ("자가 검증" / "self-audit" / "전체 스캔" / "리포지토리 스캔")
_AUDIT_SCAN_HINTS = re.compile(
    r"(self.?audit|자가.?검증|자가.?점검|레포.*스캔|repo.*scan|argos 점검|전체 점검)",
    re.IGNORECASE,
)
# 일정 봇 라우팅 — "일정/스케줄" 핵심 키워드가 있을 때만 발동.
# "인터뷰 스케줄링" 같은 문맥은 _INTERVIEW_HINTS 가 앞단에서 잡으므로 충돌 위험 낮음.
_SCHEDULE_HINTS = re.compile(r"(일정|스케줄|schedule)", re.IGNORECASE)
_SCHEDULE_TODAY_HINTS = re.compile(r"(오늘|today)", re.IGNORECASE)
_SCHEDULE_WEEK_HINTS = re.compile(r"(이번\s*주|this\s*week|금주)", re.IGNORECASE)
_SCHEDULE_UPCOMING_HINTS = re.compile(
    r"(예정|다가오는|앞으로|다음.*일정|일정.*목록|upcoming|list)",
    re.IGNORECASE,
)
_SCHEDULE_REGISTER_HINTS = re.compile(
    r"(등록|추가|잡아\s*줘|잡아주세요|만들어\s*줘|add|create|register)",
    re.IGNORECASE,
)
# "YYYY-MM-DD" 또는 "M월 D일" 패턴 추출 — 날짜검색 라우팅 보조.
_DATE_ISO_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_DATE_KR_RE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")


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

        # 명시적 self-audit 키워드 — 즉시 룰베이스 스캔으로 라우팅
        if _AUDIT_SCAN_HINTS.search(text) and not (has_ext(_CODE_EXTS) or has_image()):
            return Intent(
                bot="argos_self_audit",
                action="audit_scan",
                reason="self-audit/전체 스캔 키워드",
                confidence=0.85,
                source="rule",
            )

        # 브랜치 리뷰 트리거 — 코드 첨부/이미지 없을 때만.
        # diff vs snapshot 명시적 키워드 둘 다 검사:
        #   - SNAPSHOT 키워드 있음 → code_branch_snapshot (비용 큼, 사용자가 명시적으로 요청한 경우만)
        #   - DIFF 키워드 있음    → code_branch_diff (안전·저비용 기본값)
        #   - 브랜치 키워드만 있고 어느 쪽도 없음 → LLM 위임 (의도 모호)
        # 명시적 키워드 충돌 시 SNAPSHOT 우선 — 사용자가 명확히 적은 표현이므로.
        if _BRANCH_HINTS.search(text) and not (has_ext(_CODE_EXTS) or has_image()):
            branch_params: dict[str, Any] = {}
            branch_match = _BRANCH_NAME_RE.search(text)
            if branch_match:
                branch_params["branch"] = branch_match.group(1)
            if _SECURITY_HINTS.search(text):
                branch_params["focus"] = "security"

            if _BRANCH_FULL_HINTS.search(text):
                return Intent(
                    bot="code_sentinel",
                    action="code_branch_snapshot",
                    reason="브랜치 + 전체/스냅샷 키워드",
                    confidence=0.85,
                    params=branch_params,
                    source="rule",
                )
            if _BRANCH_DIFF_HINTS.search(text):
                return Intent(
                    bot="code_sentinel",
                    action="code_branch_diff",
                    reason="브랜치 + 변경/diff 키워드",
                    confidence=0.85,
                    params=branch_params,
                    source="rule",
                )
            # 브랜치 의도는 있는데 diff/snapshot 불명 → LLM 위임 (강제 default 피함)
            return None

        # 명시적 KISA/컴플라이언스 — 코드 첨부 없으면 PRD 매핑(audit_feature) 으로 위임.
        # Code Sentinel 의 code_kisa 와 달리 LLM 비용 0 이라 일상 질문에 적합.
        if _KISA_HINTS.search(text) and not (has_ext(_CODE_EXTS) or has_image()):
            return Intent(
                bot="argos_self_audit",
                action="audit_feature",
                reason="KISA/PIPA 키워드 + 코드 첨부 없음 → 룰베이스 매핑(LLM 0)",
                confidence=0.8,
                params={"prd_text": text},
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

        # 일정/스케줄 키워드 — 첨부 없는 경우만 (첨부 있으면 다른 봇이 우선).
        # "인터뷰 스케줄" 같이 _INTERVIEW_HINTS 가 함께 잡히는 경우 LLM 위임.
        if _SCHEDULE_HINTS.search(text) and not _INTERVIEW_HINTS.search(text):
            # 1) "오늘 일정" → schedule_today
            if _SCHEDULE_TODAY_HINTS.search(text):
                return Intent(
                    bot="schedule_bot",
                    action="schedule_today",
                    reason="오늘 + 일정 키워드",
                    confidence=0.85,
                    source="rule",
                )
            # 2) "이번 주 일정" → schedule_week
            if _SCHEDULE_WEEK_HINTS.search(text):
                return Intent(
                    bot="schedule_bot",
                    action="schedule_week",
                    reason="이번 주 + 일정 키워드",
                    confidence=0.85,
                    source="rule",
                )
            # 3) "YYYY-MM-DD" 또는 "M월 D일" 명시 → schedule_search
            iso = _DATE_ISO_RE.search(text)
            if iso:
                return Intent(
                    bot="schedule_bot",
                    action="schedule_search",
                    reason="ISO 날짜 명시 + 일정 키워드",
                    confidence=0.85,
                    params={"date": iso.group(1)},
                    source="rule",
                )
            kr = _DATE_KR_RE.search(text)
            if kr:
                # 연도 없는 한국식 표기 — 올해 기준 추정 (보수적이라 LLM 재분류 여지 남김).
                import datetime as _dt
                year = _dt.datetime.now().year
                month, day = int(kr.group(1)), int(kr.group(2))
                try:
                    iso_date = f"{year:04d}-{month:02d}-{day:02d}"
                    _dt.datetime.strptime(iso_date, "%Y-%m-%d")  # 유효성
                    return Intent(
                        bot="schedule_bot",
                        action="schedule_search",
                        reason="한국식 날짜 표기 + 일정 키워드 (올해 기준)",
                        confidence=0.7,
                        params={"date": iso_date},
                        source="rule",
                    )
                except ValueError:
                    pass
            # 4) "예정/다가오는/목록" → schedule_upcoming
            if _SCHEDULE_UPCOMING_HINTS.search(text):
                return Intent(
                    bot="schedule_bot",
                    action="schedule_upcoming",
                    reason="예정/목록 + 일정 키워드",
                    confidence=0.8,
                    source="rule",
                )
            # 5) "등록/추가/잡아줘" — title/date 파싱이 필요하므로 LLM 위임.
            if _SCHEDULE_REGISTER_HINTS.search(text):
                return None
            # 일정 키워드만 있고 액션 불명 → LLM 위임 (의도 파악 부족)
            return None

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
        # today 도 함께 노출 — schedule_register/search 가 "내일/모레" 같은 상대 날짜를
        # YYYY-MM-DD 로 변환하려면 기준 날짜가 필요. system 프롬프트에 넣으면 캐시가 깨지므로
        # user 메시지 단에서 매 호출 갱신.
        import datetime as _dt
        today_str = _dt.date.today().strftime("%Y-%m-%d")
        atts_desc = self._summarize_attachments(route_in)
        user_text = (
            f"## 오늘 날짜\n{today_str}\n\n"
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
            "## schedule_bot 입력 규칙",
            "- 날짜는 항상 `YYYY-MM-DD` 형식. 사용자가 '내일/모레/다음 주 월요일' 등 상대 표현을 쓰면",
            "  user 메시지 상단의 '오늘 날짜' 를 기준으로 변환해 params.date 에 넣는다.",
            "- 시간은 `HH:MM` 24시간 형식. '오후 2시', '14시' 모두 `14:00`.",
            "- schedule_register 시 title 은 일정 핵심 명사구만 (예: '팀 회의'). 메시지 전체 복사 금지.",
            "- guild_id 는 절대 LLM 이 채우지 말 것 — cos delegator 가 디스코드 컨텍스트에서 자동 주입.",
            "",
            "## code_sentinel 브랜치 리뷰 액션 구분 (혼동 주의)",
            "- `code_branch_diff` (안전·저비용 기본값): 사용자가 '변경', '변경사항', 'diff', '차이', 'main 대비',",
            "  '달라진 부분', 'PR 전에 봐줘', '뭐가 바뀌었는지' 같이 **차이/변경 자체**를 강조할 때.",
            "- `code_branch_snapshot` (비용 큼, 명시 요청일 때만): 사용자가 '전체', '통째', '모든 파일',",
            "  '스냅샷', '브랜치 자체', '브랜치 전부' 같이 **브랜치 전체를 통째로 보고 싶다**고 명시할 때만.",
            "- 어느 쪽인지 모호하면 항상 `code_branch_diff` (저비용·안전). snapshot 은 명백한 신호가 있을 때만.",
            "- 두 액션 모두 `params.branch` 는 필수. 사용자가 'feature/auth-rework' 같이 명시했다면 그대로,",
            "  '내 작업 브랜치' 같이 모호하면 self 로 보내 cos 가 브랜치명을 되묻게 할 것.",
            "- `params.repo` 는 'owner/repo' 형식만. 명시되지 않으면 비워둔다(default 환경변수로 fallback).",
            "- 보안 단어('보안/취약/PII' 등)가 함께 있으면 `params.focus='security'`.",
            "- 단순 코드 본문 첨부/붙여넣기(브랜치 아님) → `code_review` 로. 둘을 절대 섞지 말 것.",
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
