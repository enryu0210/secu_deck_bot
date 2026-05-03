"""공용 예외 계층.

봇 사용자에게 노출 가능한 메시지(`user_message`)와 내부 디버그용 메시지를 분리.
이렇게 해야 Discord 응답에 "API 키 없음" 같은 보안 문구를 실수로 흘리지 않는다.
"""
from __future__ import annotations


class SecuDeckError(Exception):
    """모든 봇 공용 베이스 예외."""

    # 사용자 노출 친화 메시지. 기본은 안전한 기본값.
    default_user_message = "지금 처리에 실패했어요. 잠시 후 다시 시도해 주세요."

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(message)
        self.user_message = user_message or self.default_user_message


class LLMError(SecuDeckError):
    """LLM 호출 실패 (네트워크·인증·rate limit 등)."""

    default_user_message = "AI 응답 생성에 실패했어요. 곧 자동 재시도하거나 다시 시도해 주세요."


class QuotaExceededError(SecuDeckError):
    """사용자별 일일/시간당 호출 상한 초과."""

    default_user_message = "오늘 사용 한도를 초과했어요. 내일 다시 사용해 주세요."


class BudgetExceededError(SecuDeckError):
    """봇 단위 월 비용 한도 초과 — 비핵심 기능 차단."""

    default_user_message = (
        "이번 달 비용 한도에 도달해 일부 기능을 일시 차단했어요. 관리자에게 문의해 주세요."
    )


class ConfigError(SecuDeckError):
    """필수 환경 변수 누락·YAML 파싱 실패 등 부팅 시 오류."""

    default_user_message = "봇 설정에 문제가 있어요. 관리자에게 알려주세요."
