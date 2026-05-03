"""구조화 로깅 헬퍼.

봇 전체가 동일 로거 설정을 쓰도록 강제. structlog 사용 시 JSON 출력으로 Railway 로그
검색이 쉬워진다. 환경변수 LOG_LEVEL 로 레벨 조정.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog


_CONFIGURED = False


def _configure_once() -> None:
    """한 번만 호출되어야 하는 전역 로거 설정."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()

    # 표준 logging 도 같은 포맷으로 맞춤 (discord.py 등이 표준 logging 사용)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level, logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            # Railway 로그 가독성을 위해 콘솔 렌더 사용. 운영에서 JSON 로그가 필요하면
            # JSONRenderer 로 교체.
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level, logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str, **bound: Any) -> structlog.stdlib.BoundLogger:
    """이름 + 컨텍스트 키로 바운드된 로거를 반환.

    예) ``get_logger("pitch_sharpener", bot_name="pitch_sharpener")``.
    """
    _configure_once()
    return structlog.get_logger(name).bind(**bound)
