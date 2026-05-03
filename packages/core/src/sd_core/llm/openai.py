"""OpenAI 어댑터.

라우팅 폴백(GPT-4.1 mini)으로만 사용. 메인 작업에는 거의 쓰지 않음.
"""
from __future__ import annotations

import os
from typing import Any

from sd_core.llm.types import LLMRequest, LLMResponse, Provider
from sd_core.utils.errors import ConfigError, LLMError
from sd_core.utils.logger import get_logger


_log = get_logger("sd_core.llm.openai")


class OpenAIAdapter:
    """openai SDK 래퍼."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ConfigError("OPENAI_API_KEY 환경변수가 비어 있습니다.")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ConfigError("openai 패키지가 설치되지 않았습니다.") from exc
        self.client = AsyncOpenAI(api_key=key)

    async def call(self, model: str, request: LLMRequest) -> LLMResponse:
        # OpenAI 는 system 메시지를 messages 리스트 맨 앞에 둔다.
        messages: list[dict[str, Any]] = [{"role": "system", "content": request.system}]
        messages.extend(request.messages)

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("openai_api_error", model=model, error=str(exc))
            raise LLMError(f"OpenAI API error: {exc}") from exc

        choice = response.choices[0]
        text = (choice.message.content or "").strip()

        usage = response.usage
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        # OpenAI prompt cache (있을 경우) — 신규 모델만 지원
        cached_tokens = 0
        if usage and getattr(usage, "prompt_tokens_details", None):
            cached_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0

        return LLMResponse(
            text=text,
            provider=Provider.OPENAI,
            model_used=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            raw={"finish_reason": choice.finish_reason},
        )
