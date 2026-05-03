"""인터뷰 후 기록·정리.

흐름:
1. (선택) 긴 녹취는 Gemini Flash 로 1차 압축 — 토큰 비용 절감 + Sonnet 컨텍스트 한도 보호
2. Sonnet (KOREAN_WRITING) 으로 가설 검증 + 인용 추출 (JSON 강제)
3. 결과 InterviewStorage.save() 로 저장

JSON 파싱 실패 시 raw 응답을 summary.short 에 그대로 넣어 적어도 사용자가 결과를 잃지는 않게 한다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, TaskType
from sd_core.utils.logger import get_logger

from interview_companion.interview_prep import Hypothesis
from interview_companion.storage import (
    InterviewRecord,
    InterviewStorage,
    InterviewTarget,
)


_log = get_logger("interview_companion.logger")

# 이 길이 초과 녹취만 Gemini Flash 로 1차 압축. 짧으면 바로 Sonnet 으로.
_LARGE_NOTE_THRESHOLD_CHARS = 8000

# 1차 압축 시스템 프롬프트 — 별도 파일로 분리할 만큼 길지 않아 인라인.
_FLASH_COMPRESS_SYSTEM = """\
당신은 1시간 분량 녹취를 사실만 보존해 30~40% 길이로 압축하는 한국어 트랜스크립트 정리자입니다.

규칙:
- 화자 구분 ([대표] / [인터뷰이]) 유지
- 인터뷰이의 핵심 발언은 가능한 원문 그대로 (인용 가치 보존)
- 잡담·반복·확인음("네네", "음...") 제거
- 추측·해석 추가 금지 — 들은 내용만 정리
- 출력은 "[화자] 발언" 형식 평문. 메타 코멘트 금지.
"""


@dataclass
class InterviewLogResult:
    record: InterviewRecord
    cost_krw: float
    parse_warning: str | None  # JSON 파싱 실패 시 사용자에게 노출


class InterviewLogger:
    """녹취/메모 → 정리된 InterviewRecord."""

    def __init__(
        self,
        llm: LLMRouter,
        storage: InterviewStorage,
        log_prompt_path: Path,
        get_hypotheses,
    ):
        self.llm = llm
        self.storage = storage
        self._log_prompt_path = log_prompt_path
        # 함수 콜러블로 받아 prep 의 mtime-aware 재로드 활용
        self._get_hypotheses = get_hypotheses

    async def log(
        self,
        target: InterviewTarget,
        interview_date: date,
        raw_content: str,
        user_id: str,
    ) -> InterviewLogResult:
        if not raw_content.strip():
            raise ValueError("녹취/메모 내용이 비어 있습니다.")

        total_cost = 0.0

        # 1) 긴 녹취 1차 압축 (Gemini Flash)
        if len(raw_content) > _LARGE_NOTE_THRESHOLD_CHARS:
            compressed, c_cost = await self._compress(raw_content, user_id)
            total_cost += c_cost
            normalized_notes = compressed
            _log.info(
                "raw_compressed",
                original_chars=len(raw_content),
                compressed_chars=len(compressed),
            )
        else:
            normalized_notes = raw_content

        # 2) 정리·분석 (Sonnet, JSON 강제)
        parsed, parse_warn, p_cost = await self._analyze(
            target, normalized_notes, user_id,
        )
        total_cost += p_cost

        # 3) 저장
        record = InterviewRecord(
            id=None,
            interview_number=0,  # storage.save() 에서 자동 채움
            target=target,
            interview_date=interview_date,
            raw_notes=raw_content,  # 원본 보존
            summary=parsed.get("summary") or {},
            hypotheses_results=parsed.get("hypotheses_results") or {},
            quotes=parsed.get("quotes") or [],
            user_id=user_id,
        )
        saved = await self.storage.save(record)

        return InterviewLogResult(
            record=saved,
            cost_krw=total_cost,
            parse_warning=parse_warn,
        )

    # -----------------------------------------------------------------
    async def _compress(self, raw: str, user_id: str) -> tuple[str, float]:
        """긴 녹취 → Flash 1회로 압축."""
        request = LLMRequest(
            task_type=TaskType.LARGE_CONTEXT,
            system=_FLASH_COMPRESS_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    "다음 녹취를 사실 보존 원칙으로 압축해 주세요.\n\n"
                    "--- 녹취 시작 ---\n" + raw + "\n--- 녹취 끝 ---"
                ),
            }],
            user_id=user_id,
            bot_name="interview_companion",
            max_tokens=4000,
            temperature=0.2,
        )
        response = await self.llm.call(request)
        compressed = response.text or raw
        return compressed, response.cost_krw

    async def _analyze(
        self,
        target: InterviewTarget,
        notes: str,
        user_id: str,
    ) -> tuple[dict[str, Any], str | None, float]:
        """Sonnet 호출 → JSON 파싱. 실패 시 폴백."""
        hypotheses: list[Hypothesis] = self._get_hypotheses()
        hyp_lines = [f"- {h.id}: {h.statement}" for h in hypotheses]

        system_prompt = self._read_log_prompt() + "\n\n## 가설 카탈로그\n" + "\n".join(hyp_lines)

        user_content = (
            "## 인터뷰이 정보\n"
            f"- 역할: {target.role} @ {target.company} ({target.company_size})\n"
            f"- 배경: {target.background or '미입력'}\n\n"
            "## 인터뷰 메모/녹취\n"
            f"{notes}\n\n"
            "위를 분석해 system 의 JSON 스키마 그대로 응답하세요. "
            "JSON 외 텍스트(설명·마크다운 코드블록 포함) 절대 금지."
        )

        request = LLMRequest(
            task_type=TaskType.KOREAN_WRITING,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            user_id=user_id,
            bot_name="interview_companion",
            max_tokens=2200,
            temperature=0.3,
        )
        response = await self.llm.call(request)
        parsed, warn = _safe_json_parse(response.text)
        return parsed, warn, response.cost_krw

    def _read_log_prompt(self) -> str:
        return self._log_prompt_path.read_text(encoding="utf-8") if self._log_prompt_path.exists() else ""


# ---------------------------------------------------------------------
# JSON 파싱 폴백
# ---------------------------------------------------------------------

# Sonnet 이 가끔 ```json 코드블록을 두를 수 있어 사전에 벗겨낸다.
_CODEBLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _safe_json_parse(text: str) -> tuple[dict[str, Any], str | None]:
    """JSON 파싱 시도. 실패 시 폴백 dict + 경고 메시지 반환."""
    candidate = text.strip()
    m = _CODEBLOCK_RE.search(candidate)
    if m:
        candidate = m.group(1).strip()

    # 모델이 앞뒤로 무언가 붙였을 때 첫 { 부터 마지막 } 까지만 잘라서 시도
    if not candidate.startswith("{"):
        l = candidate.find("{")
        r = candidate.rfind("}")
        if l != -1 and r != -1 and r > l:
            candidate = candidate[l : r + 1]

    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            return data, None
        return {"summary": {"short": candidate}}, "응답이 JSON 객체가 아니었어요. 원문을 요약 칸에 보관했어요."
    except json.JSONDecodeError as exc:
        _log.warning("interview_log_json_parse_failed", error=str(exc))
        return (
            {
                "summary": {"short": text[:1500]},
                "hypotheses_results": {},
                "quotes": [],
                "missed_questions": [],
                "argos_insights": [],
            },
            "정리 결과를 JSON 으로 받지 못해 원문을 요약 칸에 그대로 저장했어요.",
        )


__all__ = ["InterviewLogger", "InterviewLogResult"]
