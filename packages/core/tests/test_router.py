"""LLMRouter 테스트 — mock 어댑터로 폴백·비용 기록 동작 확인."""
from __future__ import annotations

import pytest

from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, LLMResponse, Provider, TaskType
from sd_core.tracking.cost import CostTracker
from sd_core.tracking.usage import UsageTracker
from sd_core.utils.errors import LLMError, BudgetExceededError


class _MockAdapter:
    """언제 호출됐는지 기록하는 mock."""

    def __init__(self, *, fail: bool = False, text: str = "ok"):
        self.fail = fail
        self.text = text
        self.calls: list[tuple[str, LLMRequest]] = []

    async def call(self, model: str, request: LLMRequest) -> LLMResponse:
        self.calls.append((model, request))
        if self.fail:
            raise LLMError("mock failure")
        return LLMResponse(
            text=self.text,
            provider=Provider.ANTHROPIC,
            model_used=model,
            input_tokens=100,
            output_tokens=50,
            cached_tokens=0,
        )


@pytest.mark.asyncio
async def test_first_choice_succeeds():
    cost = CostTracker("test_bot", monthly_limit_krw=10000)
    usage = UsageTracker("test_bot", daily_limit_per_user=100)
    mock = _MockAdapter()
    router = LLMRouter(cost=cost, usage=usage, anthropic_factory=lambda: mock)

    response = await router.call(LLMRequest(
        task_type=TaskType.KOREAN_WRITING,
        system="시스템 프롬프트",
        messages=[{"role": "user", "content": "안녕"}],
        user_id="u1",
        bot_name="test_bot",
    ))
    assert response.text == "ok"
    assert response.fallback_triggered is False
    assert len(mock.calls) == 1


@pytest.mark.asyncio
async def test_fallback_triggers_on_first_failure():
    """첫 후보가 실패하면 두 번째 후보로 자동 폴백."""
    cost = CostTracker("test_bot", monthly_limit_krw=10000)
    # KOREAN_WRITING 정책: [sonnet, opus] — 둘 다 anthropic
    failing = _MockAdapter(fail=False)

    # 첫 호출만 실패시키는 변종
    call_count = {"n": 0}
    original = failing.call

    async def maybe_fail(model: str, request: LLMRequest):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise LLMError("first attempt fails")
        return await original(model, request)

    failing.call = maybe_fail  # type: ignore[assignment]

    router = LLMRouter(cost=cost, anthropic_factory=lambda: failing)
    response = await router.call(LLMRequest(
        task_type=TaskType.KOREAN_WRITING,
        system="...",
        messages=[{"role": "user", "content": "x"}],
        user_id="u1",
        bot_name="test_bot",
    ))
    assert response.fallback_triggered is True


@pytest.mark.asyncio
async def test_all_failures_raise_llm_error():
    cost = CostTracker("test_bot", monthly_limit_krw=10000)
    mock = _MockAdapter(fail=True)
    router = LLMRouter(cost=cost, anthropic_factory=lambda: mock)
    with pytest.raises(LLMError):
        await router.call(LLMRequest(
            task_type=TaskType.CODE_REVIEW_COMPLEX,  # candidates 1개라 폴백 없음
            system="...",
            messages=[{"role": "user", "content": "x"}],
            user_id="u1",
            bot_name="test_bot",
        ))


@pytest.mark.asyncio
async def test_budget_exceeded_raises():
    """누적 비용이 한도 초과하면 예외."""
    cost = CostTracker("test_bot", monthly_limit_krw=0.0001)  # 매우 작은 한도
    mock = _MockAdapter()
    router = LLMRouter(cost=cost, anthropic_factory=lambda: mock)
    with pytest.raises(BudgetExceededError):
        await router.call(LLMRequest(
            task_type=TaskType.KOREAN_WRITING,
            system="...",
            messages=[{"role": "user", "content": "x"}],
            user_id="u1",
            bot_name="test_bot",
            max_tokens=10,
        ))


@pytest.mark.asyncio
async def test_cost_recorded_on_success():
    cost = CostTracker("test_bot", monthly_limit_krw=100000)
    mock = _MockAdapter()
    router = LLMRouter(cost=cost, anthropic_factory=lambda: mock)
    response = await router.call(LLMRequest(
        task_type=TaskType.KOREAN_WRITING,
        system="...",
        messages=[{"role": "user", "content": "x"}],
        user_id="u1",
        bot_name="test_bot",
    ))
    assert response.cost_krw > 0
    monthly = await cost.monthly_total()
    assert monthly > 0
