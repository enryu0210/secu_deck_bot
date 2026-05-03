"""Google Gemini 어댑터.

대용량 컨텍스트(인터뷰 누적)와 이미지 이해(디자인)에 사용.
google-genai SDK 의 비동기 API 사용.
"""
from __future__ import annotations

import os
from typing import Any

from sd_core.llm.types import LLMRequest, LLMResponse, Provider
from sd_core.utils.errors import ConfigError, LLMError
from sd_core.utils.logger import get_logger


_log = get_logger("sd_core.llm.gemini")


class GeminiAdapter:
    """Google google-genai SDK 래퍼."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise ConfigError("GOOGLE_API_KEY 환경변수가 비어 있습니다.")
        # 지연 import — google-genai 가 설치 안 되어도 다른 어댑터는 동작하도록.
        try:
            from google import genai  # type: ignore
        except ImportError as exc:
            raise ConfigError("google-genai 패키지가 설치되지 않았습니다.") from exc
        self.client = genai.Client(api_key=key)
        self._genai = genai

    async def call(self, model: str, request: LLMRequest) -> LLMResponse:
        """Gemini 호출. system + user messages → contents 변환."""
        # Gemini 는 system_instruction 으로 시스템 프롬프트 전달.
        contents = self._convert_messages(request.messages, request.images)

        try:
            from google.genai import types as genai_types  # type: ignore
            response = await self.client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    system_instruction=request.system,
                    max_output_tokens=request.max_tokens,
                    temperature=request.temperature,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — SDK 예외 종류가 많아 광범위 잡음
            _log.warning("gemini_api_error", model=model, error=str(exc))
            raise LLMError(f"Gemini API error: {exc}") from exc

        text = (response.text or "").strip()

        # 토큰 사용량 — Gemini SDK 응답에서 추출
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
        cached_tokens = getattr(usage, "cached_content_token_count", 0) if usage else 0

        return LLMResponse(
            text=text,
            provider=Provider.GOOGLE,
            model_used=model,
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or 0,
            cached_tokens=cached_tokens or 0,
            raw={"finish_reason": getattr(response, "finish_reason", None)},
        )

    def _convert_messages(
        self,
        messages: list[dict[str, Any]],
        images: list[bytes] | None,
    ) -> list[Any]:
        """messages → Gemini Content 리스트.

        Gemini 의 role 은 ``user`` 와 ``model`` 만 인정. assistant → model 매핑.
        """
        from google.genai import types as genai_types  # type: ignore

        contents: list[Any] = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "assistant":
                role = "model"
            text = msg.get("content", "")
            if not isinstance(text, str):
                # 블록 리스트인 경우 텍스트만 결합 (멀티모달은 마지막 user 에 붙임)
                text = "\n".join(
                    str(b.get("text", "")) for b in text if isinstance(b, dict)
                )
            contents.append(
                genai_types.Content(role=role, parts=[genai_types.Part(text=text)])
            )

        # 이미지 첨부 — 마지막 user 메시지에 추가
        if images:
            last_user_idx = next(
                (i for i in range(len(contents) - 1, -1, -1) if contents[i].role == "user"),
                None,
            )
            if last_user_idx is not None:
                parts = list(contents[last_user_idx].parts)
                for img in images:
                    parts.append(
                        genai_types.Part.from_bytes(data=img, mime_type="image/png")
                    )
                contents[last_user_idx] = genai_types.Content(role="user", parts=parts)

        return contents
