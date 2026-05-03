"""LLM 라우팅·어댑터 레이어.

봇 코드는 항상 ``LLMRouter``만 사용해야 한다 (직접 SDK 호출 금지).
"""
from sd_core.llm.types import (
    LLMRequest,
    LLMResponse,
    TaskType,
    Provider,
)
from sd_core.llm.router import LLMRouter

__all__ = [
    "LLMRequest",
    "LLMResponse",
    "TaskType",
    "Provider",
    "LLMRouter",
]
