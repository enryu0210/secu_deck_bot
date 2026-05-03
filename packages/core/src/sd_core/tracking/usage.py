"""사용자별 호출 횟수 쿼터.

비용 한도(``CostTracker``)와 별도로, "한 사용자가 하루에 몇 번 호출할 수 있는가"를 제한한다.
이건 비용보다는 어뷰즈/실수 방지용 (예: 사용자가 같은 명령을 100번 연타).
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from dataclasses import dataclass

from sd_core.utils.errors import QuotaExceededError
from sd_core.utils.logger import get_logger


@dataclass
class _UserCounter:
    day_key: str = ""
    counts: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.counts is None:
            self.counts = defaultdict(int)


class UsageTracker:
    """일일 호출 횟수 카운터. in-memory only (단순함 우선)."""

    def __init__(self, bot_name: str, daily_limit_per_user: int = 50):
        self.bot_name = bot_name
        self.daily_limit_per_user = daily_limit_per_user
        self._counter = _UserCounter()
        self._lock = asyncio.Lock()
        self._log = get_logger("sd_core.usage", bot_name=bot_name)

    async def check_and_increment(self, user_id: str) -> int:
        """호출 1건 카운트. 한도 초과 시 예외."""
        async with self._lock:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if self._counter.day_key != today:
                self._counter.day_key = today
                self._counter.counts.clear()

            current = self._counter.counts[user_id] + 1
            if current > self.daily_limit_per_user:
                self._log.warning(
                    "user_daily_quota_exceeded",
                    user_id=user_id,
                    limit=self.daily_limit_per_user,
                )
                raise QuotaExceededError(
                    f"User {user_id} exceeded daily quota of {self.daily_limit_per_user}"
                )
            self._counter.counts[user_id] = current
            return current

    async def user_count_today(self, user_id: str) -> int:
        async with self._lock:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if self._counter.day_key != today:
                return 0
            return self._counter.counts.get(user_id, 0)
