"""리뷰 오케스트레이션.

세 가지 모드:
- full_review: 6 페르소나 병렬 → 종합
- quick_diagnosis: Sonnet 1회 호출로 6대 원인 충족도 평가
- focused_review: 단일 페르소나 깊이 리뷰

병렬 호출 시 Anthropic rate limit 방어를 위해 router 가 내부 Semaphore(3) 적용 중.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from sd_core.context.argos import ArgosContext
from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, TaskType
from sd_core.personas.base import Persona
from sd_core.personas.loader import PersonaLoader

from pitch_sharpener.persona_runner import PersonaRunner, PersonaReview
from pitch_sharpener.synthesizer import Synthesizer


@dataclass
class FullReviewResult:
    persona_reviews: list[PersonaReview]
    synthesis_text: str
    total_cost_krw: float
    fallback_count: int


@dataclass
class QuickDiagnosisResult:
    text: str
    cost_krw: float


@dataclass
class FocusedReviewResult:
    persona_review: PersonaReview


class ReviewEngine:
    """봇 진입점에서 호출되는 메인 엔진."""

    def __init__(
        self,
        llm: LLMRouter,
        argos: ArgosContext,
        personas_dir: Path,
        prompts_dir: Path,
    ):
        self.llm = llm
        self.argos = argos
        self.prompts_dir = prompts_dir
        self.personas_dir = personas_dir
        self._loader = PersonaLoader()
        self.personas: list[Persona] = self._loader.load_all(personas_dir)
        self.persona_by_id: dict[str, Persona] = {p.id: p for p in self.personas}
        self.synthesizer = Synthesizer(llm, prompts_dir)
        self._quick_prompt = self._read(prompts_dir / "quick_diagnosis.md")

    # -----------------------------------------------------------------
    # 풀 리뷰
    # -----------------------------------------------------------------
    async def full_review(self, document_text: str, user_id: str) -> FullReviewResult:
        """6 페르소나 병렬 호출 → 종합."""
        # 너무 긴 본문은 6번 반복되어 비용 폭발하므로 적절히 절단.
        # 한국어 ~ 30,000자(약 15,000 토큰) 까지가 안전.
        excerpt = document_text if len(document_text) <= 30000 else (
            document_text[:28000] + "\n\n[...본문 절단됨...]"
        )

        runners = [
            PersonaRunner(self.llm, self.argos, p, self.prompts_dir) for p in self.personas
        ]

        # asyncio.gather 로 6개 병렬. router 내부 Semaphore(3) 가 동시 호출을 3건으로 제한.
        # 일부 페르소나가 실패해도 나머지는 진행되도록 return_exceptions=True.
        results = await asyncio.gather(
            *[r.review(excerpt, user_id) for r in runners],
            return_exceptions=True,
        )

        reviews: list[PersonaReview] = []
        for runner, result in zip(runners, results):
            if isinstance(result, BaseException):
                # 실패 시 에러를 페르소나 리뷰처럼 포장 (사용자에게 일부라도 전달)
                reviews.append(PersonaReview(
                    persona_id=runner.persona.id,
                    persona_name=runner.persona.name,
                    persona_emoji=runner.persona.emoji,
                    content=f"⚠️ 이 페르소나 리뷰 생성에 실패했어요: {result}",
                    cost_krw=0.0,
                    fallback_triggered=False,
                ))
            else:
                reviews.append(result)

        # 종합 — 실패한 페르소나가 1개 이상이어도 나머지로 종합 시도
        synthesis = await self.synthesizer.combine(reviews, excerpt, user_id)

        total_cost = sum(r.cost_krw for r in reviews) + synthesis.cost_krw
        fallback_count = sum(1 for r in reviews if r.fallback_triggered)

        return FullReviewResult(
            persona_reviews=reviews,
            synthesis_text=synthesis.overall_text,
            total_cost_krw=total_cost,
            fallback_count=fallback_count,
        )

    # -----------------------------------------------------------------
    # 빠른 진단
    # -----------------------------------------------------------------
    async def quick_diagnosis(
        self,
        document_text: str,
        user_id: str,
    ) -> QuickDiagnosisResult:
        """Sonnet 1회 호출로 6대 원인 충족도만 빠르게 평가."""
        excerpt = document_text if len(document_text) <= 12000 else (
            document_text[:11500] + "\n\n[...본문 절단됨...]"
        )

        request = LLMRequest(
            task_type=TaskType.KOREAN_WRITING,
            system=self._quick_prompt,
            messages=[{
                "role": "user",
                "content": (
                    "다음 사업계획서를 빠르게 진단해 출력 형식에 맞춰 응답해 주세요.\n\n"
                    f"{excerpt}"
                ),
            }],
            user_id=user_id,
            bot_name="pitch_sharpener",
            max_tokens=600,
            temperature=0.3,
        )
        response = await self.llm.call(request)
        return QuickDiagnosisResult(text=response.text, cost_krw=response.cost_krw)

    # -----------------------------------------------------------------
    # 단일 페르소나 깊이 리뷰
    # -----------------------------------------------------------------
    async def focused_review(
        self,
        document_text: str,
        persona_id: str,
        user_id: str,
    ) -> FocusedReviewResult:
        if persona_id not in self.persona_by_id:
            raise KeyError(f"Unknown persona: {persona_id}")
        persona = self.persona_by_id[persona_id]
        runner = PersonaRunner(self.llm, self.argos, persona, self.prompts_dir)
        review = await runner.review(document_text, user_id)
        return FocusedReviewResult(persona_review=review)

    # -----------------------------------------------------------------
    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""
