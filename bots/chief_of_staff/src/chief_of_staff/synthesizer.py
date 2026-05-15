"""cos 톤으로 응답 포장 — 위임 인트로 + self 직접 답변.

설계 결정:
- **위임 인트로는 LLM 호출 안 함**. 라우팅 1회당 Haiku + 봇 호출(평균 Sonnet)이 이미 발생.
  여기에 다시 Sonnet 으로 1줄 인트로를 만들면 비용·지연 둘 다 손해.
  → ``ROUTABLE_ACTIONS`` 카탈로그를 그대로 활용해 정적 템플릿으로 만든다.

- **self 답변만 LLM 호출**. cos 가 직접 처리하는 가벼운 일반 질문(인사·메타 질문 등)은
  Sonnet 으로 짧게 답변. Argos 컨텍스트는 가능한 한 시스템 프롬프트에 포함해
  prompt caching 길이(>=1024 토큰) 확보.

응답은 항상 ``SynthesisResult`` 로 표준화 — ui.py 가 임베드 변환을 담당하므로
여기선 텍스트와 비용만 다룬다.
"""
from __future__ import annotations

from dataclasses import dataclass

from sd_core.context.argos import ArgosContext
from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, TaskType
from sd_core.utils.errors import LLMError
from sd_core.utils.logger import get_logger

from chief_of_staff.intent_router import Intent
from chief_of_staff.ui import BOT_DISPLAY


_log = get_logger("chief_of_staff.synthesizer")


# 액션별 한국어 인트로 — IntentRouter 카탈로그에 새 (bot, action) 추가 시 함께 갱신.
_ACTION_INTRO: dict[str, str] = {
    "pitch_quick":       "사업계획서를 빠르게 진단해 드리도록 연결할게요.",
    "pitch_focus":       "지정하신 페르소나로 사업계획서를 깊이 살펴볼게요.",
    "code_review":       "코드 리뷰로 연결합니다.",
    "code_test":         "단위 테스트 자동 생성으로 연결합니다.",
    "code_kisa":         "KISA·개인정보보호법 정합성 점검으로 연결합니다.",
    "interview_prep":    "고객 인터뷰 가이드를 준비해 볼게요.",
    "interview_insight": "누적된 인터뷰를 다시 분석해 인사이트를 정리해 드릴게요.",
    "design_check":      "DS 일관성 검사로 연결합니다.",
    "design_spec":       "개발 핸드오프용 spec 문서를 만들어 드릴게요.",
    "design_copy":       "UX 카피 검토로 연결합니다.",
    "audit_scan":        "Argos 레포 즉시 자가 점검을 실행할게요 (룰베이스, LLM 미호출).",
    "audit_feature":     "PRD 키워드 기반으로 관련 법령을 매핑해 드릴게요 (룰베이스, LLM 미호출).",
    "schedule_today":    "오늘 일정을 가져올게요.",
    "schedule_week":     "이번 주 일정을 정리해 드릴게요.",
    "schedule_upcoming": "다가오는 일정 목록을 보여드릴게요.",
    "schedule_search":   "지정하신 날짜의 일정을 조회할게요.",
    "schedule_register": "팀 일정으로 등록해 드릴게요.",
}


@dataclass
class SynthesisResult:
    """ui.py 가 임베드를 만들 때 쓰는 표준 결과."""

    intro: str           # cos 의 1~2 문장 인트로
    body: str            # self 답변이거나 위임 봇의 summary
    cost_krw: float = 0.0   # cos 자체가 발생시킨 비용만 (위임 비용은 ui 푸터에서 별도 표기)


class Synthesizer:
    """cos 응답 합성기. 위임 인트로와 self 답변을 한 곳에서 만든다."""

    def __init__(
        self,
        llm: LLMRouter,
        argos: ArgosContext,
        *,
        bot_name: str = "chief_of_staff",
    ):
        self.llm = llm
        self.argos = argos
        self.bot_name = bot_name

    # -----------------------------------------------------------------
    # 위임 인트로 — 정적 템플릿. LLM 호출 X.
    # -----------------------------------------------------------------
    def make_delegation_intro(self, intent: Intent) -> str:
        """Intent 정보만으로 cos 인트로 텍스트 작성.

        - 봇 이모지 + 표시명을 포함
        - 액션별 정해진 한국어 문구
        - confidence 가 낮으면 (< 0.5) "맞나요?" 톤으로 부드럽게
        """
        emoji, name = BOT_DISPLAY.get(intent.bot, ("🤖", intent.bot))
        head = _ACTION_INTRO.get(intent.action, "관련 봇으로 연결합니다.")

        if intent.confidence and intent.confidence < 0.5:
            return f"{emoji} **{name}** 으로 연결해 볼게요. {head}\n_(의도가 모호해서 결과가 빗나갈 수 있어요. 다르면 다시 알려주세요.)_"
        return f"{emoji} **{name}** 으로 연결합니다. {head}"

    # -----------------------------------------------------------------
    # self 답변 — cos 가 직접 답하는 가벼운 일반 질문
    # -----------------------------------------------------------------
    async def answer_self(
        self,
        user_text: str,
        user_id: str,
    ) -> SynthesisResult:
        """cos 가 직접 답변. Sonnet 1회 호출."""
        if not user_text or not user_text.strip():
            return SynthesisResult(
                intro="",
                body="무엇을 도와드릴까요? `@cos` 멘션과 함께 요청해 주세요.",
                cost_krw=0.0,
            )

        system = self._build_self_system_prompt()
        try:
            response = await self.llm.call(
                LLMRequest(
                    task_type=TaskType.KOREAN_WRITING,
                    system=system,
                    messages=[{"role": "user", "content": user_text.strip()}],
                    user_id=user_id,
                    bot_name=self.bot_name,
                    max_tokens=600,
                    temperature=0.4,
                )
            )
        except LLMError as exc:
            _log.warning("self_answer_llm_failed", error=str(exc))
            return SynthesisResult(
                intro="",
                body="지금은 답변을 만들지 못했어요. 잠시 후 다시 멘션해 주세요.",
                cost_krw=0.0,
            )

        return SynthesisResult(
            intro="",
            body=(response.text or "").strip() or "(빈 응답)",
            cost_krw=response.cost_krw,
        )

    # -----------------------------------------------------------------
    # 시스템 프롬프트 — Argos 컨텍스트 포함해 ≥1024 토큰 채워 prompt cache 확보.
    # -----------------------------------------------------------------
    def _build_self_system_prompt(self) -> str:
        argos_block = self.argos.get_summary() or "(Argos_Context.md 비어 있거나 미배치)"
        # CLAUDE.md 함정³: caching 활성화 위해 시스템 프롬프트 길이 충분히 확보.
        return "\n".join([
            "당신은 Secu Deck 의 'Chief of Staff(cos)' 봇입니다.",
            "5개 전문 봇(Pitch Sharpener / Code Sentinel / Interview Companion / Design Echo / Argos Self-Audit)의",
            "단일 진입점이며, 위임 가치가 낮은 가벼운 일반 질문에만 직접 답변합니다.",
            "",
            "## 톤",
            "- 한국어, 차분하고 군더더기 없는 비서 톤.",
            "- 모호한 단정 금지. 모르면 '확인 필요' 라고 명시.",
            "- 답변은 6문장 이내, 필요 시 2~5개 짧은 불릿.",
            "",
            "## 역할 경계",
            "- 사업계획서 본문 진단·페르소나 리뷰 → Pitch Sharpener 에 위임 (당신이 직접 하지 말 것).",
            "- 코드 리뷰·테스트 생성·KISA 점검 → Code Sentinel.",
            "- 고객 인터뷰 가이드·누적 인사이트 → Interview Companion.",
            "- 디자인 시안·spec·UX 카피 → Design Echo.",
            "- 위 영역에 해당하는 요청을 받았는데 self 로 라우팅된 경우, 짧게 안내하고",
            "  사용자가 명시적으로 첨부·정보를 보내달라고 요청하라.",
            "",
            "## 답변 규약",
            "- 두괄식. 첫 문장에 결론·제안.",
            "- 자기소개·인사 반복 금지.",
            "- 마크다운 헤더(##, ###) 사용 금지. 굵게(**...**), 불릿(-) 정도만.",
            "- 디스코드 임베드에 표시되므로 표(table) 와 코드블록 남용 자제.",
            "",
            "## Argos 제품 컨텍스트 (참조용)",
            argos_block,
        ])


__all__ = ["Synthesizer", "SynthesisResult"]
