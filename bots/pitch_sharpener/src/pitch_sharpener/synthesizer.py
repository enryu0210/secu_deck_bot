"""6 페르소나 리뷰 → 종합 등급 + Top 3 Action."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, TaskType

from pitch_sharpener.persona_runner import PersonaReview


@dataclass
class SynthesisResult:
    overall_text: str       # 종합 결과 텍스트 (등급 + 충족도 + Top 3)
    cost_krw: float


class Synthesizer:
    """6개 PersonaReview 를 받아 한 번의 LLM 호출로 종합."""

    def __init__(self, llm: LLMRouter, prompts_dir: Path):
        self.llm = llm
        self._prompt = self._read(prompts_dir / "synthesizer.md")

    async def combine(
        self,
        reviews: list[PersonaReview],
        document_excerpt: str,
        user_id: str,
    ) -> SynthesisResult:
        """페르소나 리뷰 6건 + 문서 발췌 → 종합 평가."""
        review_block = "\n\n".join(
            f"## {r.persona_emoji} {r.persona_name}\n{r.content}"
            for r in reviews
        )

        user_content = (
            "## 사업계획서 발췌 (상위 부분만)\n"
            f"{document_excerpt[:3000]}\n\n"
            "## 6 심사위원 리뷰\n"
            f"{review_block}\n\n"
            "위 리뷰를 종합해 출력 형식에 정확히 맞춰 응답해 주세요."
        )

        request = LLMRequest(
            task_type=TaskType.KOREAN_WRITING,
            system=self._prompt,
            messages=[{"role": "user", "content": user_content}],
            user_id=user_id,
            bot_name="pitch_sharpener",
            max_tokens=1200,
            temperature=0.4,
        )
        response = await self.llm.call(request)
        return SynthesisResult(overall_text=response.text, cost_krw=response.cost_krw)

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""
