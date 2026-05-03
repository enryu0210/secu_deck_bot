"""단일 페르소나로 사업계획서를 리뷰하는 러너.

각 페르소나는 자기 시스템 프롬프트(페르소나 카드 + Argos 컨텍스트 + 베이스)로 호출된다.
시스템 프롬프트가 길고 6번 반복 호출되므로 Prompt Caching 효과가 매우 크다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sd_core.context.argos import ArgosContext
from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, TaskType
from sd_core.personas.base import Persona


@dataclass
class PersonaReview:
    """단일 페르소나 리뷰 결과."""

    persona_id: str
    persona_name: str
    persona_emoji: str
    content: str
    cost_krw: float
    fallback_triggered: bool


class PersonaRunner:
    """주어진 페르소나로 한 건의 리뷰를 수행."""

    def __init__(
        self,
        llm: LLMRouter,
        argos: ArgosContext,
        persona: Persona,
        prompts_dir: Path,
    ):
        self.llm = llm
        self.argos = argos
        self.persona = persona
        self._base_prompt = self._read(prompts_dir / "system_base.md")

    async def review(self, document_text: str, user_id: str) -> PersonaReview:
        """document_text 를 1회 호출로 리뷰."""
        system_prompt = self._build_system_prompt()

        # 사용자 메시지 — 사업계획서 본문. 매우 길면 모델이 컨텍스트 한계에 닿을 수 있으므로
        # review_engine 단계에서 적절히 잘라 보내야 한다.
        user_content = (
            "다음 사업계획서를 당신의 정체성과 출력 형식에 맞게 리뷰해 주세요.\n"
            "본문이 길면 가장 중요한 약점 3개에 집중해 주세요.\n\n"
            f"--- 사업계획서 시작 ---\n{document_text}\n--- 사업계획서 끝 ---"
        )

        request = LLMRequest(
            task_type=TaskType.KOREAN_WRITING,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            user_id=user_id,
            bot_name="pitch_sharpener",
            max_tokens=1500,
            temperature=0.5,  # 일관성 우선, 창의성 낮게
        )
        response = await self.llm.call(request)

        return PersonaReview(
            persona_id=self.persona.id,
            persona_name=self.persona.name,
            persona_emoji=self.persona.emoji,
            content=response.text,
            cost_krw=response.cost_krw,
            fallback_triggered=response.fallback_triggered,
        )

    # -----------------------------------------------------------------
    def _build_system_prompt(self) -> str:
        """공통 베이스 + 페르소나 카드 + Argos 요약 결합."""
        return "\n\n".join([
            self._base_prompt,
            self.persona.to_system_prompt(),
            "# Argos 제품 맥락",
            self.argos.get_summary(max_tokens=1500),
            "# 출력 규칙",
            "- 길이는 페르소나의 output_format 을 따르되 6~10문장 이내.",
            "- 한국어로 작성.",
            "- 추상적 칭찬·일반론 금지.",
        ])

    @staticmethod
    def _read(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")
