"""LLMRouter — 봇이 LLM 에 접근하는 단일 진입점.

책임:
1. TaskType 별 1순위/폴백 모델 정책 적용
2. 어댑터 호출 + 실패 시 폴백 자동 시도
3. 비용 기록 (CostTracker) — 한도 초과면 예외 발생
4. 사용자 일일 호출 횟수 (UsageTracker)

봇 코드는 절대 직접 anthropic.Anthropic / google.genai / openai.AsyncOpenAI 를 호출하면 안 된다.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sd_core.llm.types import LLMRequest, LLMResponse, Provider, TaskType
from sd_core.tracking.cost import CostTracker
from sd_core.tracking.usage import UsageTracker
from sd_core.utils.errors import LLMError, SecuDeckError
from sd_core.utils.logger import get_logger


# ---------------------------------------------------------------------
# 모델 정책 — TaskType → (provider, model) 후보 리스트
# 첫 번째가 1순위, 실패 시 다음 후보 순차 시도.
# 모델 ID 는 2026.04 추정. 빌드/배포 시 각 공급자 문서에서 검증할 것.
# ---------------------------------------------------------------------
MODEL_POLICY: dict[TaskType, list[tuple[Provider, str]]] = {
    TaskType.KOREAN_WRITING: [
        (Provider.ANTHROPIC, "claude-sonnet-4-5"),
        (Provider.ANTHROPIC, "claude-opus-4-5"),
    ],
    TaskType.CODE_REVIEW_SIMPLE: [
        (Provider.ANTHROPIC, "claude-haiku-4-5"),
        (Provider.ANTHROPIC, "claude-sonnet-4-5"),
    ],
    TaskType.CODE_REVIEW_COMPLEX: [
        (Provider.ANTHROPIC, "claude-sonnet-4-5"),
    ],
    TaskType.VISION_DESIGN: [
        (Provider.GOOGLE, "gemini-2.5-flash"),
        (Provider.ANTHROPIC, "claude-sonnet-4-5"),
    ],
    TaskType.LARGE_CONTEXT: [
        (Provider.GOOGLE, "gemini-2.5-flash"),
        (Provider.GOOGLE, "gemini-2.5-pro"),
    ],
    TaskType.INSIGHT_EXTRACTION: [
        (Provider.ANTHROPIC, "claude-sonnet-4-5"),
    ],
    TaskType.ROUTING: [
        (Provider.ANTHROPIC, "claude-haiku-4-5"),
        (Provider.OPENAI, "gpt-4.1-mini"),
    ],
}


@dataclass
class _AdapterRegistry:
    """어댑터 인스턴스를 lazy 하게 만들어 보관 (필요한 공급자만 초기화)."""

    anthropic: object | None = None
    google: object | None = None
    openai: object | None = None


class LLMRouter:
    """모델 선택·폴백·비용 추적의 통합 진입점.

    봇별로 1개씩 만든다. CostTracker 는 봇별로 다르므로 외부에서 주입 받는다.
    """

    def __init__(
        self,
        cost: CostTracker,
        usage: UsageTracker | None = None,
        # 테스트에서 모킹 가능하도록 어댑터 클래스 주입 가능
        anthropic_factory=None,
        google_factory=None,
        openai_factory=None,
    ):
        self.cost = cost
        self.usage = usage
        self.bot_name = cost.bot_name
        self._registry = _AdapterRegistry()
        self._log = get_logger("sd_core.router", bot_name=self.bot_name)
        # 어댑터 생성 함수 (지연 초기화)
        self._anthropic_factory = anthropic_factory or self._default_claude_factory
        self._google_factory = google_factory or self._default_gemini_factory
        self._openai_factory = openai_factory or self._default_openai_factory
        # 어댑터 동시성 제한 — Anthropic rate limit 방어용
        self._anthropic_sem = asyncio.Semaphore(3)

    # --- 기본 팩토리 (지연 import 로 의존 누락 시 다른 공급자 영향 X) ---
    @staticmethod
    def _default_claude_factory():
        from sd_core.llm.claude import ClaudeAdapter
        return ClaudeAdapter()

    @staticmethod
    def _default_gemini_factory():
        from sd_core.llm.gemini import GeminiAdapter
        return GeminiAdapter()

    @staticmethod
    def _default_openai_factory():
        from sd_core.llm.openai import OpenAIAdapter
        return OpenAIAdapter()

    def _get_adapter(self, provider: Provider):
        """공급자별 어댑터 lazy init."""
        if provider == Provider.ANTHROPIC:
            if self._registry.anthropic is None:
                self._registry.anthropic = self._anthropic_factory()
            return self._registry.anthropic
        if provider == Provider.GOOGLE:
            if self._registry.google is None:
                self._registry.google = self._google_factory()
            return self._registry.google
        if provider == Provider.OPENAI:
            if self._registry.openai is None:
                self._registry.openai = self._openai_factory()
            return self._registry.openai
        raise LLMError(f"Unknown provider: {provider}")

    async def call(self, request: LLMRequest) -> LLMResponse:
        """LLM 호출 메인. 사용자 쿼터 체크 → 모델 정책 시도 → 비용 기록."""
        # 1. 사용자 일일 호출 횟수 체크 (UsageTracker 가 있으면)
        if self.usage is not None:
            await self.usage.check_and_increment(request.user_id)

        # 2. 강제 모델 지정이 있으면 그것만 사용, 아니면 정책 후보 사용
        if request.force_provider and request.force_model:
            candidates = [(request.force_provider, request.force_model)]
        else:
            candidates = MODEL_POLICY.get(request.task_type, [])
            if not candidates:
                raise LLMError(f"No model policy for task_type={request.task_type}")

        last_error: Exception | None = None
        for idx, (provider, model) in enumerate(candidates):
            try:
                adapter = self._get_adapter(provider)
            except SecuDeckError as exc:
                # 어댑터 초기화 실패(예: API 키 없음) → 다음 후보로
                self._log.warning(
                    "adapter_init_failed",
                    provider=provider.value,
                    error=str(exc),
                )
                last_error = exc
                continue

            try:
                # Anthropic 만 동시성 제한 (다른 공급자는 rate 여유)
                if provider == Provider.ANTHROPIC:
                    async with self._anthropic_sem:
                        response = await adapter.call(model, request)
                else:
                    response = await adapter.call(model, request)
            except LLMError as exc:
                self._log.warning(
                    "llm_call_failed",
                    provider=provider.value,
                    model=model,
                    attempt=idx,
                    error=str(exc),
                )
                last_error = exc
                continue

            # 3. 비용 기록 — 한도 초과 시 BudgetExceededError 가 여기서 발생
            cost_krw = await self.cost.record(
                user_id=request.user_id,
                model=model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cached_tokens=response.cached_tokens,
            )
            response.cost_krw = cost_krw
            response.fallback_triggered = idx > 0

            self._log.info(
                "llm_call_ok",
                provider=provider.value,
                model=model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cached_tokens=response.cached_tokens,
                cost_krw=cost_krw,
                fallback=response.fallback_triggered,
            )
            return response

        # 모든 후보 실패
        raise LLMError(
            f"All model candidates failed for task_type={request.task_type}. "
            f"Last error: {last_error}"
        )
