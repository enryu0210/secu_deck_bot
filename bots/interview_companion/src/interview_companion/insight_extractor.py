"""누적 인터뷰 패턴 분석.

모든 인터뷰 요약/가설검증/인용 을 통합 컨텍스트로 묶어 Gemini 2.5 Flash 로 1회 호출.
원본 raw_notes 는 보내지 않고 정리된 요약만 보내 토큰·민감정보 노출을 줄인다.

병렬 호출이 아니라 단일 호출이므로 router 의 Semaphore 영향 없음.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, TaskType
from sd_core.utils.errors import LLMError
from sd_core.utils.logger import get_logger

from interview_companion.interview_prep import Hypothesis
from interview_companion.storage import InterviewRecord, InterviewStorage


_log = get_logger("interview_companion.insight")


@dataclass
class InsightReport:
    text: str
    cost_krw: float
    interview_count: int


class InsightExtractor:
    def __init__(
        self,
        llm: LLMRouter,
        storage: InterviewStorage,
        prompt_path: Path,
        get_hypotheses,
    ):
        self.llm = llm
        self.storage = storage
        self._prompt_path = prompt_path
        self._get_hypotheses = get_hypotheses

    async def analyze_all(self, user_id: str) -> InsightReport:
        records = await self.storage.list_for_user(user_id, limit=200)
        if not records:
            raise LLMError(
                "분석할 인터뷰가 없어요.",
                user_message="아직 저장된 인터뷰가 없어요. `/interview log` 로 먼저 1건 이상 기록해 주세요.",
            )

        hypotheses = self._get_hypotheses()
        context = self._build_context(records, hypotheses)
        system_prompt = self._read_prompt()

        request = LLMRequest(
            task_type=TaskType.LARGE_CONTEXT,
            system=system_prompt,
            messages=[{"role": "user", "content": context}],
            user_id=user_id,
            bot_name="interview_companion",
            max_tokens=3000,
            temperature=0.3,
        )
        response = await self.llm.call(request)
        return InsightReport(
            text=response.text,
            cost_krw=response.cost_krw,
            interview_count=len(records),
        )

    # -----------------------------------------------------------------
    @staticmethod
    def _build_context(
        records: list[InterviewRecord],
        hypotheses: list[Hypothesis],
    ) -> str:
        """LLM 입력 — 가설 카탈로그 + 인터뷰 요약 묶음.

        raw_notes 는 포함하지 않음 (개인정보 + 토큰 절약).
        """
        lines: list[str] = ["# 가설 카탈로그"]
        for h in hypotheses:
            lines.append(f"- **{h.id}** (P{h.priority}): {h.statement}")

        lines.append("\n# 인터뷰 요약 모음")
        for rec in records:
            lines.append(f"\n## 인터뷰 #{rec.interview_number} — {rec.target.display}")
            lines.append(f"날짜: {rec.interview_date.isoformat() if rec.interview_date else '미상'}")

            summary = rec.summary or {}
            short = summary.get("short")
            if short:
                lines.append(f"요약: {short}")
            key_points = summary.get("key_points") or []
            if key_points:
                lines.append("핵심 포인트:")
                for kp in key_points:
                    lines.append(f"  - {kp}")

            hyp_results = rec.hypotheses_results or {}
            if hyp_results:
                lines.append("가설 검증:")
                for hyp_id, body in hyp_results.items():
                    if not isinstance(body, dict):
                        continue
                    verdict = body.get("verdict", "?")
                    evidence = body.get("evidence", "")
                    lines.append(f"  - {hyp_id}: {verdict} — {evidence}")

            quotes = rec.quotes or []
            if quotes:
                lines.append("주요 인용:")
                for q in quotes[:5]:  # 너무 길어지지 않게 5개까지만
                    text = q.get("text", "")
                    hyp_id = q.get("hypothesis_id") or "-"
                    lines.append(f'  - "{text}" ({hyp_id})')

        lines.append(
            "\n위 자료를 바탕으로 system 의 출력 형식을 그대로 따라 누적 분석을 작성하세요."
        )
        return "\n".join(lines)

    def _read_prompt(self) -> str:
        return self._prompt_path.read_text(encoding="utf-8") if self._prompt_path.exists() else ""


__all__ = ["InsightExtractor", "InsightReport"]
