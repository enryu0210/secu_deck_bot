"""봇 간 내부 HTTP API — cos(Chief of Staff) 가 봇을 호출할 때 쓰는 클라이언트.

서버 측은 ``internal_api.InternalAPIServer``. 응답 포맷도 그쪽 docstring 참조.

설계:
- 봇별 base_url 매핑 + 공유 시크릿. cos 의 환경변수에서 읽음.
- 타임아웃 60초 (LLM 호출 포함이라 넉넉히).
- 실패 시 표준화된 dict 반환 — cos 측은 항상 dict 응답을 기대하면 됨.
"""
from __future__ import annotations

import os
from typing import Any

from sd_core.utils.errors import ConfigError, SecuDeckError
from sd_core.utils.logger import get_logger


_log = get_logger("sd_core.internal_client")


class InternalAPIClient:
    """봇별 base_url 을 보관하고 ``invoke(bot, action, payload)`` 로 호출."""

    DEFAULT_TIMEOUT_S = 60.0

    def __init__(
        self,
        bot_urls: dict[str, str] | None = None,
        secret: str | None = None,
        timeout_s: float | None = None,
    ):
        # 봇별 URL — 명시적으로 받지 않으면 환경변수에서 자동 로드.
        self.bot_urls = bot_urls if bot_urls is not None else self._read_urls_from_env()
        self.secret = secret if secret is not None else os.getenv("INTERNAL_API_SECRET", "")
        self.timeout_s = timeout_s or self.DEFAULT_TIMEOUT_S
        self._client: Any | None = None  # httpx.AsyncClient (lazy)

    @staticmethod
    def _read_urls_from_env() -> dict[str, str]:
        """``BOT_URL_<SUFFIX>`` 환경변수에서 봇별 URL 읽기.

        suffix 는 cost.py 의 suffix_map 과 동일 — PITCH/CODE/INTERVIEW/DESIGN/AUDIT.
        URL 미설정 봇은 dict 에 포함시키지 않음 → 호출 시 ConfigError.
        """
        mapping = {
            "pitch_sharpener": os.getenv("BOT_URL_PITCH"),
            "code_sentinel": os.getenv("BOT_URL_CODE"),
            "interview_companion": os.getenv("BOT_URL_INTERVIEW"),
            "design_echo": os.getenv("BOT_URL_DESIGN"),
            "argos_self_audit": os.getenv("BOT_URL_AUDIT"),
        }
        return {k: v for k, v in mapping.items() if v}

    async def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:
                raise ConfigError(
                    "httpx 미설치 — cos 봇 pyproject.toml 의 dependencies 에 "
                    "'httpx>=0.27' 추가 후 'uv sync' 재실행."
                ) from exc
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def invoke(
        self,
        bot: str,
        action: str,
        payload: dict[str, Any],
        user_id: str,
    ) -> dict[str, Any]:
        """봇에 위임 호출. 표준화 dict 반환 (실패 시에도)."""
        if not self.secret:
            raise ConfigError("INTERNAL_API_SECRET 환경변수 미설정")
        base = self.bot_urls.get(bot)
        if not base:
            raise ConfigError(f"봇 '{bot}' 의 BOT_URL_* 환경변수가 설정되지 않았어요.")

        url = base.rstrip("/") + "/api/invoke"
        body = {"action": action, "user_id": user_id, "payload": payload}
        headers = {"X-Internal-Secret": self.secret, "Content-Type": "application/json"}

        client = await self._ensure_client()
        try:
            resp = await client.post(url, json=body, headers=headers)
        except Exception as exc:  # noqa: BLE001 — httpx 예외 외에도 광범위 캐치
            _log.warning("internal_invoke_network_error", bot=bot, action=action, error=str(exc))
            raise SecuDeckError(
                f"{bot} 호출 실패: {exc}",
                user_message=f"{bot} 봇과 통신에 실패했어요. 잠시 후 다시 시도해 주세요.",
            ) from exc

        if resp.status_code == 401:
            raise SecuDeckError(
                "shared secret 불일치 — 환경변수 점검 필요",
                user_message="봇 간 인증에 실패했어요. 관리자에게 알려주세요.",
            )
        if resp.status_code == 503:
            raise SecuDeckError(
                f"{bot} INTERNAL_API_SECRET 미설정",
                user_message=f"{bot} 봇 설정에 문제가 있어요. 관리자에게 알려주세요.",
            )
        if resp.status_code == 404:
            # 알 수 없는 action — cos 측 라우팅 버그 가능성
            raise SecuDeckError(
                f"{bot} 가 action '{action}' 을 모릅니다.",
                user_message=f"{bot} 봇이 이 작업을 지원하지 않아요.",
            )
        if resp.status_code >= 400:
            _log.warning(
                "internal_invoke_http_error",
                bot=bot,
                action=action,
                status=resp.status_code,
                body=resp.text[:500],
            )
            raise SecuDeckError(
                f"{bot} HTTP {resp.status_code}: {resp.text[:200]}",
                user_message=f"{bot} 봇이 응답에 실패했어요.",
            )

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise SecuDeckError(
                f"{bot} 응답 JSON 파싱 실패: {exc}",
                user_message=f"{bot} 봇 응답을 해석할 수 없었어요.",
            ) from exc

        if not isinstance(data, dict):
            raise SecuDeckError(
                f"{bot} 응답이 dict 형식이 아님: {type(data).__name__}",
                user_message=f"{bot} 봇 응답 형식이 예상과 달라요.",
            )
        return data
