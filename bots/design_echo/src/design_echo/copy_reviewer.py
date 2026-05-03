"""UX 라이팅 검토.

Sonnet 1회. tone_guide.yaml 을 system 에 그대로 첨부해 일관 톤 유지.
한국어 톤 분석은 Gemini 보다 Sonnet 이 안정적이라 모델 강제 X (router 정책 그대로).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, TaskType

from design_echo.design_system import DesignSystem


@dataclass
class CopyReview:
    text: str
    cost_krw: float


class CopyReviewer:
    def __init__(
        self,
        llm: LLMRouter,
        ds: DesignSystem,
        copy_prompt_path: Path,
        base_prompt_path: Path,
    ):
        self.llm = llm
        self.ds = ds
        self._copy_prompt_path = copy_prompt_path
        self._base_prompt_path = base_prompt_path

    async def review(
        self,
        screen_context: str,
        purpose: str,
        current_copy: str,
        user_id: str,
    ) -> CopyReview:
        if not current_copy.strip():
            raise ValueError("검토할 카피가 비어 있습니다.")

        system_prompt = self._build_system_prompt()
        user_content = (
            "## 화면 컨텍스트\n"
            f"{screen_context.strip() or '미입력'}\n\n"
            "## 카피 목적\n"
            f"{purpose.strip() or '미입력'}\n\n"
            "## 현재 카피\n"
            f"```\n{current_copy.strip()}\n```\n\n"
            "system 의 출력 형식을 그대로 따라 검토와 3가지 대안을 작성해 주세요."
        )

        request = LLMRequest(
            task_type=TaskType.KOREAN_WRITING,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            user_id=user_id,
            bot_name="design_echo",
            max_tokens=1500,
            temperature=0.6,  # 대안 다양성 위해 약간 높임
        )
        response = await self.llm.call(request)
        return CopyReview(text=response.text, cost_krw=response.cost_krw)

    # -----------------------------------------------------------------
    def _build_system_prompt(self) -> str:
        base = self._read(self._base_prompt_path)
        copy = self._read(self._copy_prompt_path)
        tone = self.ds.tone()
        # tone_guide 전체를 JSON 으로 첨부 (Sonnet 이 잘 읽음, 캐시도 잘 됨)
        tone_block = "## Argos 톤 가이드 (전체)\n```yaml\n" + json.dumps(tone, ensure_ascii=False, indent=2) + "\n```"
        return "\n\n".join([base, copy, tone_block])

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""


__all__ = ["CopyReviewer", "CopyReview"]
