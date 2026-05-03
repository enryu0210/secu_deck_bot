"""Postgres 풀 헬퍼.

DATABASE_URL 환경변수가 있을 때만 활성화. 없으면 ``get_pool`` 이 None 반환.
Phase 2(인터뷰·디자인 봇)부터 본격 사용.
"""
from __future__ import annotations

import os
from typing import Any

from sd_core.utils.logger import get_logger


_log = get_logger("sd_core.storage.postgres")


# 초기 마이그레이션 — Stage 1 에서 한 번 실행하면 됨.
MIGRATIONS_SQL = """
-- LLM 호출 비용 기록 (모든 봇 공유)
CREATE TABLE IF NOT EXISTS llm_calls (
    id SERIAL PRIMARY KEY,
    bot_name TEXT NOT NULL,
    user_id TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INT,
    output_tokens INT,
    cached_tokens INT,
    cost_krw NUMERIC(10, 4),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_bot_time ON llm_calls(bot_name, created_at);
CREATE INDEX IF NOT EXISTS idx_llm_calls_user_time ON llm_calls(user_id, created_at);
"""


class PostgresPool:
    """asyncpg 풀의 얇은 래퍼. 풀 lifecycle + 편의 메서드.

    봇별로 전역 1개를 공유 (``get_pool()``).
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: Any = None  # asyncpg.Pool 지연 import

    async def connect(self) -> None:
        if self._pool is not None:
            return
        try:
            import asyncpg  # type: ignore
        except ImportError as exc:
            raise RuntimeError("asyncpg 패키지가 설치되지 않았습니다.") from exc
        self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
        _log.info("postgres_connected")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def execute(self, query: str, *args: Any) -> str:
        assert self._pool is not None, "PostgresPool not connected"
        return await self._pool.execute(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Any:
        assert self._pool is not None, "PostgresPool not connected"
        return await self._pool.fetchrow(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        assert self._pool is not None, "PostgresPool not connected"
        return list(await self._pool.fetch(query, *args))

    async def run_migrations(self, sql: str = MIGRATIONS_SQL) -> None:
        """초기 스키마 적용. idempotent (CREATE IF NOT EXISTS)."""
        assert self._pool is not None, "PostgresPool not connected"
        async with self._pool.acquire() as conn:
            await conn.execute(sql)
        _log.info("postgres_migrations_done")


_GLOBAL_POOL: PostgresPool | None = None


async def get_pool() -> PostgresPool | None:
    """전역 풀 lazy 초기화. DATABASE_URL 없으면 None 반환."""
    global _GLOBAL_POOL
    if _GLOBAL_POOL is not None:
        return _GLOBAL_POOL
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return None
    pool = PostgresPool(dsn)
    await pool.connect()
    _GLOBAL_POOL = pool
    return pool
