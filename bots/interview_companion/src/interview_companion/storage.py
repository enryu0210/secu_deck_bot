"""인터뷰 영속 저장소.

Postgres 가 있으면 DB, 없으면 in-memory 폴백 (개발/단순 운영 호환).
sd_core.storage.postgres.PostgresPool 을 그대로 활용해 비용 추적과 같은 풀을 공유한다.

스키마 정의는 ``bots/interview_companion/migrations/001_interviews.sql`` 참고.
JSONB 컬럼(summary, hypotheses_results, quotes) 은 dict/list 로 다룬다.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sd_core.storage.postgres import PostgresPool, get_pool
from sd_core.utils.logger import get_logger


_log = get_logger("interview_companion.storage")


@dataclass
class InterviewTarget:
    """인터뷰 대상자 정보 — 슬래시 커맨드 입력 그대로."""

    name: str
    role: str
    company: str
    company_size: str  # "30인", "100인 이하" 등 자유 텍스트
    background: str = ""

    # 익명화 권장: 이니셜·역할만 저장
    @property
    def display(self) -> str:
        return f"{self.role} @ {self.company} ({self.company_size})"


@dataclass
class InterviewRecord:
    """저장된 인터뷰 1건. JSONB 필드는 파이썬 dict/list 그대로."""

    id: int | None
    interview_number: int
    target: InterviewTarget
    interview_date: date
    raw_notes: str
    summary: dict[str, Any] = field(default_factory=dict)
    hypotheses_results: dict[str, Any] = field(default_factory=dict)
    quotes: list[dict[str, Any]] = field(default_factory=list)
    user_id: str = ""
    created_at: datetime | None = None


class InterviewStorage:
    """인터뷰 CRUD. Postgres 우선, 없으면 in-memory.

    ``init()`` 을 봇 부팅 시 한 번 호출해 풀 연결 + 마이그레이션을 적용한다.
    """

    # in-memory 폴백 — 사용자별 리스트 (사용자 격리)
    def __init__(self):
        self.pool: PostgresPool | None = None
        self._mem: dict[str, list[InterviewRecord]] = defaultdict(list)
        self._mem_seq: int = 0

    async def init(self, migration_path: Path | None = None) -> None:
        """봇 부팅 시 1회. 풀 가져오고 마이그레이션 적용.

        Postgres 가 없는 환경에서는 그냥 in-memory 로 동작.
        """
        self.pool = await get_pool()
        if self.pool is None:
            _log.warning("postgres_unavailable_using_memory")
            return
        # 1) 공통 마이그레이션 (llm_calls 등) — 멱등이라 재호출 안전
        await self.pool.run_migrations()
        # 2) 인터뷰 전용 마이그레이션
        if migration_path and migration_path.exists():
            sql = migration_path.read_text(encoding="utf-8")
            await self.pool.run_migrations(sql)
            _log.info("interview_migrations_applied", path=str(migration_path))

    # -----------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------
    async def save(self, record: InterviewRecord) -> InterviewRecord:
        """신규 저장 또는 업데이트. record.id 가 None 이면 INSERT."""
        if self.pool is None:
            return self._save_memory(record)

        # 다음 interview_number 계산 (사용자별 1부터). 별도 시퀀스로 두면 정확하지만
        # 단순함을 위해 현재 사용자 최대값 + 1.
        if record.interview_number <= 0:
            row = await self.pool.fetchrow(
                "SELECT COALESCE(MAX(interview_number), 0) AS m FROM interviews WHERE user_id = $1",
                record.user_id,
            )
            record.interview_number = (row["m"] if row else 0) + 1

        row = await self.pool.fetchrow(
            """
            INSERT INTO interviews
              (interview_number, target_name, target_role, target_company,
               target_company_size, interview_date, raw_notes,
               summary, hypotheses_results, quotes, user_id)
            VALUES
              ($1, $2, $3, $4, $5, $6, $7,
               $8::jsonb, $9::jsonb, $10::jsonb, $11)
            RETURNING id, created_at
            """,
            record.interview_number,
            record.target.name,
            record.target.role,
            record.target.company,
            record.target.company_size,
            record.interview_date,
            record.raw_notes,
            json.dumps(record.summary, ensure_ascii=False),
            json.dumps(record.hypotheses_results, ensure_ascii=False),
            json.dumps(record.quotes, ensure_ascii=False),
            record.user_id,
        )
        record.id = int(row["id"])
        record.created_at = row["created_at"]
        _log.info(
            "interview_saved",
            id=record.id,
            user_id=record.user_id,
            number=record.interview_number,
        )
        return record

    async def list_for_user(self, user_id: str, limit: int = 100) -> list[InterviewRecord]:
        """사용자가 만든 모든 인터뷰. 누적 분석에서 사용."""
        if self.pool is None:
            return list(self._mem[user_id])[:limit]

        rows = await self.pool.fetch(
            """
            SELECT id, interview_number, target_name, target_role, target_company,
                   target_company_size, interview_date, raw_notes,
                   summary, hypotheses_results, quotes, user_id, created_at
            FROM interviews
            WHERE user_id = $1
            ORDER BY interview_date DESC, id DESC
            LIMIT $2
            """,
            user_id, limit,
        )
        return [self._row_to_record(r) for r in rows]

    async def find_by_target_name(
        self,
        user_id: str,
        target_name: str,
    ) -> InterviewRecord | None:
        """이름으로 가장 최근 인터뷰 찾기 (`/interview log` 에서 후처리 시)."""
        if self.pool is None:
            for rec in reversed(self._mem[user_id]):
                if rec.target.name == target_name:
                    return rec
            return None

        row = await self.pool.fetchrow(
            """
            SELECT id, interview_number, target_name, target_role, target_company,
                   target_company_size, interview_date, raw_notes,
                   summary, hypotheses_results, quotes, user_id, created_at
            FROM interviews
            WHERE user_id = $1 AND target_name = $2
            ORDER BY id DESC
            LIMIT 1
            """,
            user_id, target_name,
        )
        return self._row_to_record(row) if row else None

    async def search_quotes(
        self,
        user_id: str,
        keyword: str | None = None,
        hypothesis_id: str | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """인용 발언 검색. LLM 불필요 — Postgres JSONB 또는 in-memory 필터."""
        records = await self.list_for_user(user_id, limit=200)
        results: list[dict[str, Any]] = []
        kw = (keyword or "").strip().lower()

        for rec in records:
            for quote in rec.quotes:
                text = str(quote.get("text", ""))
                hyp = quote.get("hypothesis_id")
                if hypothesis_id and hyp != hypothesis_id:
                    continue
                if kw and kw not in text.lower():
                    continue
                results.append({
                    **quote,
                    "interview_number": rec.interview_number,
                    "interview_id": rec.id,
                    "target": rec.target.display,
                })
                if len(results) >= limit:
                    return results
        return results

    # -----------------------------------------------------------------
    # 유틸
    # -----------------------------------------------------------------
    def _save_memory(self, record: InterviewRecord) -> InterviewRecord:
        """Postgres 없을 때 폴백."""
        self._mem_seq += 1
        record.id = self._mem_seq
        if record.interview_number <= 0:
            record.interview_number = len(self._mem[record.user_id]) + 1
        record.created_at = datetime.now(timezone.utc)
        self._mem[record.user_id].append(record)
        return record

    @staticmethod
    def _row_to_record(row: Any) -> InterviewRecord:
        """asyncpg Record → InterviewRecord. JSONB 자동 dict 변환됨."""
        target = InterviewTarget(
            name=row["target_name"] or "",
            role=row["target_role"] or "",
            company=row["target_company"] or "",
            company_size=row["target_company_size"] or "",
        )
        # asyncpg 가 jsonb 를 dict 로 디코드해 주지만, str 로 들어오는 경우도 방어
        summary = _coerce_json(row["summary"], dict)
        hyp = _coerce_json(row["hypotheses_results"], dict)
        quotes = _coerce_json(row["quotes"], list)

        return InterviewRecord(
            id=int(row["id"]),
            interview_number=int(row["interview_number"] or 0),
            target=target,
            interview_date=row["interview_date"],
            raw_notes=row["raw_notes"] or "",
            summary=summary or {},
            hypotheses_results=hyp or {},
            quotes=quotes or [],
            user_id=row["user_id"] or "",
            created_at=row["created_at"],
        )


def _coerce_json(value: Any, expected: type) -> Any:
    """JSONB 칼럼 값이 dict/list 가 아닐 때 안전 디코드."""
    if value is None:
        return expected()
    if isinstance(value, expected):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return expected()
    return expected()
