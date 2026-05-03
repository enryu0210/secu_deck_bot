"""디자인 일관성 체크.

흐름:
1. Gemini Flash Vision 으로 시안에서 토큰 추출 (JSON)
2. design_system 로 비교 → diffs
3. 시안 텍스트가 있으면 Sonnet 으로 톤 체크 추가 (가성비 우선 — 텍스트 없으면 스킵)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, TaskType
from sd_core.utils.logger import get_logger

from design_echo.design_system import CheckSummary, DesignSystem


_log = get_logger("design_echo.consistency")

# Gemini 가 가끔 ```json 으로 감싸 응답 → 코드블록 사전 제거
_CODEBLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass
class ToneIssue:
    text: str
    issue: str
    suggestion: str


@dataclass
class CheckResult:
    extracted: dict       # 시안에서 LLM 이 본 raw 추출 결과
    summary: CheckSummary
    tone_issues: list[ToneIssue] = field(default_factory=list)
    cost_krw: float = 0.0
    parse_warning: str | None = None


class ConsistencyChecker:
    def __init__(
        self,
        llm: LLMRouter,
        ds: DesignSystem,
        check_prompt_path: Path,
        base_prompt_path: Path,
    ):
        self.llm = llm
        self.ds = ds
        self._check_prompt_path = check_prompt_path
        self._base_prompt_path = base_prompt_path

    async def check(self, image_bytes: bytes, user_id: str) -> CheckResult:
        if not image_bytes:
            raise ValueError("이미지가 비어 있습니다.")

        total_cost = 0.0

        # 1) Vision 추출
        extracted, parse_warn, vis_cost = await self._extract(image_bytes, user_id)
        total_cost += vis_cost

        # 2) DS 비교 (LLM 호출 없음)
        summary = self.ds.compare(extracted)

        # 3) 톤 체크 — 추출된 텍스트가 있을 때만 (가성비)
        tone_issues: list[ToneIssue] = []
        texts = [t for t in (extracted.get("texts") or []) if isinstance(t, str) and t.strip()]
        if texts:
            tone_issues, tone_cost = await self._check_tone(texts, user_id)
            total_cost += tone_cost

        return CheckResult(
            extracted=extracted,
            summary=summary,
            tone_issues=tone_issues,
            cost_krw=total_cost,
            parse_warning=parse_warn,
        )

    # -----------------------------------------------------------------
    async def _extract(
        self,
        image_bytes: bytes,
        user_id: str,
    ) -> tuple[dict, str | None, float]:
        """Vision 호출 → JSON dict. 실패 시 빈 dict + 경고."""
        system_prompt = self._read(self._check_prompt_path)

        request = LLMRequest(
            task_type=TaskType.VISION_DESIGN,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": "첨부된 디자인 시안을 분석해 system 의 JSON 스키마 그대로 응답해 주세요.",
            }],
            images=[image_bytes],
            user_id=user_id,
            bot_name="design_echo",
            max_tokens=1800,
            temperature=0.2,
        )
        response = await self.llm.call(request)

        parsed, warn = _safe_json(response.text)
        return parsed, warn, response.cost_krw

    async def _check_tone(
        self,
        texts: list[str],
        user_id: str,
    ) -> tuple[list[ToneIssue], float]:
        """추출된 화면 텍스트 → Sonnet 으로 톤 위반 검사 (간단 JSON)."""
        tone_yaml = self.ds.tone()
        forbidden = (tone_yaml.get("forbidden") or {})
        principles = (tone_yaml.get("principles") or [])
        examples_bad = (tone_yaml.get("examples") or {}).get("bad") or []

        # 시스템 — 베이스 + 톤 가이드 압축본 (캐시 효율 위해 일정 길이 보장)
        system_prompt = (
            self._read(self._base_prompt_path)
            + "\n\n## 이번 호출의 톤 검사 미션\n"
            + "이미지에서 추출된 한국어 UI 텍스트들이 Argos 톤 가이드를 따르는지 검사하세요.\n\n"
            + "## Argos 톤 원칙\n"
            + "\n".join(f"- {p}" for p in principles)
            + "\n\n## 금기\n"
            + json.dumps(forbidden, ensure_ascii=False, indent=2)
            + "\n\n## bad 예시\n"
            + "\n".join(f"- {b}" for b in examples_bad)
            + "\n\n## 출력\n"
            "JSON 배열만. 각 항목 {text, issue, suggestion}. 위반 없으면 빈 배열 [] 반환.\n"
            "JSON 외 텍스트(설명·코드블록) 절대 금지."
        )

        user_content = (
            "다음 화면 텍스트들을 검사해 주세요:\n\n"
            + "\n".join(f'- "{t}"' for t in texts[:30])
        )

        request = LLMRequest(
            task_type=TaskType.KOREAN_WRITING,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            user_id=user_id,
            bot_name="design_echo",
            max_tokens=900,
            temperature=0.3,
        )
        response = await self.llm.call(request)

        parsed = _safe_json_list(response.text)
        issues: list[ToneIssue] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            issues.append(ToneIssue(
                text=str(item.get("text", "")),
                issue=str(item.get("issue", "")),
                suggestion=str(item.get("suggestion", "")),
            ))
        return issues, response.cost_krw

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""


# ---------------------------------------------------------------------
# JSON 폴백
# ---------------------------------------------------------------------
def _safe_json(text: str) -> tuple[dict, str | None]:
    candidate = (text or "").strip()
    m = _CODEBLOCK_RE.search(candidate)
    if m:
        candidate = m.group(1).strip()
    if not candidate.startswith("{"):
        l = candidate.find("{")
        r = candidate.rfind("}")
        if l != -1 and r != -1 and r > l:
            candidate = candidate[l : r + 1]
    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            return data, None
    except json.JSONDecodeError as exc:
        _log.warning("vision_json_parse_failed", error=str(exc))
    return {}, "시안에서 토큰 추출 결과를 JSON 으로 받지 못했어요. 비교를 건너뛰었습니다."


def _safe_json_list(text: str) -> list:
    candidate = (text or "").strip()
    m = _CODEBLOCK_RE.search(candidate)
    if m:
        candidate = m.group(1).strip()
    if not candidate.startswith("["):
        l = candidate.find("[")
        r = candidate.rfind("]")
        if l != -1 and r != -1 and r > l:
            candidate = candidate[l : r + 1]
    try:
        data = json.loads(candidate)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError as exc:
        _log.warning("tone_json_parse_failed", error=str(exc))
    return []


__all__ = ["ConsistencyChecker", "CheckResult", "ToneIssue"]
