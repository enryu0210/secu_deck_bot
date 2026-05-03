"""비용 추적.

원칙:
- 모델 가격표는 한 곳(이 파일)에서 관리. 가격 변동 시 여기만 수정.
- DB가 없는 환경(로컬 개발·초기 배포)에서도 동작하도록 in-memory 폴백 제공.
- 한도 초과 시 ``BudgetExceededError`` 던져 봇이 비핵심 기능 차단하게 함.
"""
from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sd_core.utils.errors import BudgetExceededError
from sd_core.utils.logger import get_logger

if TYPE_CHECKING:
    from sd_core.storage.postgres import PostgresPool


# ---------------------------------------------------------------------
# 가격표 — 2026.04 기준 추정. 실제 빌드 시점에 각 공급자 문서로 검증.
# 단위: USD per 1M tokens. cache_read 는 캐시 적중 토큰 가격.
# ---------------------------------------------------------------------
PRICING_PER_1M_TOKENS_USD: dict[str, dict[str, float]] = {
    # Anthropic Claude
    "claude-sonnet-4-5": {"input": 3.00,  "output": 15.00, "cache_read": 0.30},
    "claude-haiku-4-5":  {"input": 1.00,  "output": 5.00,  "cache_read": 0.10},
    "claude-opus-4-5":   {"input": 15.00, "output": 75.00, "cache_read": 1.50},
    # Google Gemini
    "gemini-2.5-flash":  {"input": 0.30,  "output": 2.50,  "cache_read": 0.075},
    "gemini-2.5-pro":    {"input": 1.25,  "output": 10.00, "cache_read": 0.31},
    # OpenAI
    "gpt-4.1-mini":      {"input": 0.40,  "output": 1.60,  "cache_read": 0.10},
}

# 환율 — 빌드/배포 시점에 갱신
USD_TO_KRW = 1380.0


def calculate_cost_krw(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> float:
    """모델·토큰 수로 KRW 비용 계산.

    캐시된 토큰은 input 가격이 아닌 cache_read 가격 적용 (저렴).
    가격표에 없는 모델은 0원으로 처리하지 말고 보수적 추정치(Sonnet 가격) 사용.
    """
    pricing = PRICING_PER_1M_TOKENS_USD.get(model)
    if pricing is None:
        # 알 수 없는 모델은 가장 비싼 Sonnet 가격으로 추정해 한도 초과 위험 회피
        pricing = PRICING_PER_1M_TOKENS_USD["claude-sonnet-4-5"]

    fresh_input = max(0, input_tokens - cached_tokens)
    cost_usd = (
        fresh_input / 1_000_000 * pricing["input"]
        + cached_tokens / 1_000_000 * pricing["cache_read"]
        + output_tokens / 1_000_000 * pricing["output"]
    )
    return round(cost_usd * USD_TO_KRW, 4)


@dataclass
class _InMemoryRecord:
    """DB 없을 때 폴백용 기록 구조."""

    bot_monthly_total_krw: float = 0.0
    bot_month_key: str = ""
    user_daily_total_krw: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    user_day_key: str = ""


class CostTracker:
    """봇별 월 한도 + 사용자별 일일 호출 비용 추적.

    Postgres 가 있으면 DB 사용, 없으면 in-memory 로 동작.
    Phase 1A 에서는 in-memory 도 충분 (사용자 1명 + 짧은 기간).
    """

    def __init__(
        self,
        bot_name: str,
        monthly_limit_krw: float | None = None,
        pool: "PostgresPool | None" = None,
    ):
        self.bot_name = bot_name
        self.monthly_limit_krw = monthly_limit_krw or self._read_limit_from_env(bot_name)
        self.pool = pool
        self._mem = _InMemoryRecord()
        self._lock = asyncio.Lock()
        self._log = get_logger("sd_core.cost", bot_name=bot_name)

    @staticmethod
    def _read_limit_from_env(bot_name: str) -> float:
        """환경변수 ``COST_MONTHLY_LIMIT_KRW_<BOT>`` 에서 한도 읽기."""
        suffix_map = {
            "pitch_sharpener": "PITCH",
            "code_sentinel": "CODE",
            "interview_companion": "INTERVIEW",
            "design_echo": "DESIGN",
            "chief_of_staff": "COS",
            "argos_self_audit": "AUDIT",
        }
        suffix = suffix_map.get(bot_name, bot_name.upper())
        return float(os.getenv(f"COST_MONTHLY_LIMIT_KRW_{suffix}", "50000"))

    async def record(
        self,
        user_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
    ) -> float:
        """LLM 호출 1건 기록. 한도 초과면 예외 발생.

        반환값은 이번 호출 비용(KRW). 호출자(router)는 LLMResponse 에 그대로 담아 반환.
        """
        cost = calculate_cost_krw(model, input_tokens, output_tokens, cached_tokens)

        async with self._lock:
            # in-memory 누적
            now = datetime.now(timezone.utc)
            month_key = now.strftime("%Y-%m")
            day_key = now.strftime("%Y-%m-%d")

            if self._mem.bot_month_key != month_key:
                self._mem.bot_month_key = month_key
                self._mem.bot_monthly_total_krw = 0.0
            if self._mem.user_day_key != day_key:
                self._mem.user_day_key = day_key
                self._mem.user_daily_total_krw.clear()

            self._mem.bot_monthly_total_krw += cost
            self._mem.user_daily_total_krw[user_id] += cost
            monthly_total = self._mem.bot_monthly_total_krw

        # DB 가 붙어 있으면 비동기 저장 (실패해도 호출 자체는 성공시켜야 함)
        if self.pool is not None:
            try:
                await self.pool.execute(
                    """
                    INSERT INTO llm_calls
                        (bot_name, user_id, model, input_tokens, output_tokens, cached_tokens, cost_krw)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    self.bot_name, user_id, model,
                    input_tokens, output_tokens, cached_tokens, cost,
                )
            except Exception as exc:  # noqa: BLE001
                # DB 실패는 운영 신호이지만 사용자 응답은 막지 않는다
                self._log.warning("cost_db_write_failed", error=str(exc))

        # 한도 체크 — 90% 도달하면 경고 로그, 100% 초과면 예외
        ratio = monthly_total / self.monthly_limit_krw if self.monthly_limit_krw else 0
        if ratio >= 1.0:
            self._log.error(
                "monthly_budget_exceeded",
                total_krw=monthly_total,
                limit_krw=self.monthly_limit_krw,
            )
            raise BudgetExceededError(
                f"{self.bot_name} monthly budget exceeded: "
                f"{monthly_total:.0f} / {self.monthly_limit_krw:.0f} KRW"
            )
        if ratio >= 0.9:
            self._log.warning(
                "monthly_budget_90pct",
                total_krw=monthly_total,
                limit_krw=self.monthly_limit_krw,
            )

        return cost

    async def monthly_total(self) -> float:
        """이번 달 봇 총 비용. DB 우선, 없으면 in-memory."""
        if self.pool is not None:
            try:
                row = await self.pool.fetchrow(
                    """
                    SELECT COALESCE(SUM(cost_krw), 0) AS total
                    FROM llm_calls
                    WHERE bot_name = $1
                      AND created_at >= date_trunc('month', NOW())
                    """,
                    self.bot_name,
                )
                if row is not None:
                    return float(row["total"])
            except Exception as exc:  # noqa: BLE001
                self._log.warning("cost_db_read_failed", error=str(exc))
        return self._mem.bot_monthly_total_krw

    async def user_today(self, user_id: str) -> float:
        """사용자 오늘 누적 비용."""
        if self.pool is not None:
            try:
                row = await self.pool.fetchrow(
                    """
                    SELECT COALESCE(SUM(cost_krw), 0) AS total
                    FROM llm_calls
                    WHERE bot_name = $1
                      AND user_id = $2
                      AND created_at >= date_trunc('day', NOW())
                    """,
                    self.bot_name, user_id,
                )
                if row is not None:
                    return float(row["total"])
            except Exception as exc:  # noqa: BLE001
                self._log.warning("cost_db_read_failed", error=str(exc))
        return self._mem.user_daily_total_krw.get(user_id, 0.0)
