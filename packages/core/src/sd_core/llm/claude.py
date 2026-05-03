"""Anthropic Claude 어댑터.

핵심 기능: Prompt Caching(``cache_control``)을 자동 적용해 Argos 컨텍스트·페르소나
시스템 프롬프트의 재사용 비용을 75~90% 절감한다.

주의: 시스템 프롬프트가 너무 짧으면(약 1024 토큰 미만) Anthropic 이 캐싱을 거절할 수 있다.
이 경우 캐시 미적용으로 폴백 (일반 호출).
"""
from __future__ import annotations

import os
from typing import Any

from anthropic import AsyncAnthropic
from anthropic._exceptions import APIError, APIStatusError

from sd_core.llm.types import LLMRequest, LLMResponse, Provider
from sd_core.utils.errors import ConfigError, LLMError
from sd_core.utils.logger import get_logger


_log = get_logger("sd_core.llm.claude")


class ClaudeAdapter:
    """Anthropic SDK 직접 호출 래퍼."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ConfigError("ANTHROPIC_API_KEY 환경변수가 비어 있습니다.")
        self.client = AsyncAnthropic(api_key=key)

    async def call(self, model: str, request: LLMRequest) -> LLMResponse:
        """Claude 메시지 호출. 실패 시 LLMError 로 변환."""
        # 시스템 프롬프트는 list[블록] 형태로 보내야 cache_control 가능.
        system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": request.system,
            }
        ]
        if request.enable_cache and len(request.system) > 200:
            # 캐시 적용 (5분 ephemeral). 아주 짧은 프롬프트는 캐싱 의미 없으므로 생략.
            system_blocks[0]["cache_control"] = {"type": "ephemeral"}

        # messages 변환 — Claude 도 OpenAI 와 같은 role/content 구조이므로 거의 그대로 사용.
        # 단, 멀티모달(이미지)은 별도 변환.
        messages = self._convert_messages(request.messages, request.images)

        try:
            response = await self.client.messages.create(
                model=model,
                system=system_blocks,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        except APIStatusError as exc:
            _log.warning("claude_api_status_error", status=exc.status_code, model=model)
            raise LLMError(f"Claude API status {exc.status_code}: {exc.message}") from exc
        except APIError as exc:
            _log.warning("claude_api_error", model=model, error=str(exc))
            raise LLMError(f"Claude API error: {exc}") from exc

        # 응답 텍스트 결합 (멀티 블록 가능)
        text_parts = [
            block.text for block in response.content
            if getattr(block, "type", "") == "text"
        ]
        text = "\n".join(text_parts).strip()

        usage = response.usage
        # cache_read_input_tokens 가 있으면 캐시 적중. 없으면 0.
        cached = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        # input_tokens 는 캐시 제외 토큰. cache_creation 도 입력에 포함 비용.
        input_total = (usage.input_tokens or 0) + cache_creation + cached

        return LLMResponse(
            text=text,
            provider=Provider.ANTHROPIC,
            model_used=model,
            input_tokens=input_total,
            output_tokens=usage.output_tokens or 0,
            cached_tokens=cached,
            raw={
                "stop_reason": response.stop_reason,
                "id": response.id,
            },
        )

    @staticmethod
    def _convert_messages(
        messages: list[dict[str, Any]],
        images: list[bytes] | None,
    ) -> list[dict[str, Any]]:
        """messages 리스트를 Claude 포맷으로 변환. 이미지는 마지막 user 메시지에 첨부."""
        if not images:
            return messages

        converted = list(messages)
        # 마지막 user 메시지를 찾아 이미지 블록을 prepend
        for idx in range(len(converted) - 1, -1, -1):
            if converted[idx].get("role") == "user":
                content = converted[idx].get("content", "")
                # content 가 문자열이면 블록 리스트로 변환
                if isinstance(content, str):
                    blocks: list[dict[str, Any]] = [{"type": "text", "text": content}]
                else:
                    blocks = list(content)

                import base64
                for img in images:
                    blocks.insert(0, {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            # 보수적으로 PNG 가정. 실제 디자인 봇은 PNG/JPG 입력만 받음.
                            "media_type": "image/png",
                            "data": base64.b64encode(img).decode("ascii"),
                        },
                    })
                converted[idx] = {"role": "user", "content": blocks}
                break
        return converted
