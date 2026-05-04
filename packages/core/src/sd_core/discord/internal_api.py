"""봇 간 내부 HTTP API — Chief of Staff 가 5봇을 위임 호출할 때 쓰는 서버 측 헬퍼.

설계 원칙:
- **봇별 1개씩 띄움**: 각 봇이 자기 핵심 능력을 ``register(action, handler)`` 로 노출.
- **공유 시크릿 인증**: ``INTERNAL_API_SECRET`` 환경변수 일치 시에만 호출 허용.
- **discord.py 와 같은 이벤트 루프**: ``await server.start()`` 가 uvicorn 을 background task 로 돌림 → 봇과 공존.
- **fastapi/uvicorn 은 옵셔널**: sd_core 코어 의존성에 넣지 않고 lazy import. 봇별 pyproject.toml 에 추가.

호출자(cos)에게 돌려주는 표준 응답 형식 (dict):
    {
      "ok": true|false,
      "summary": "디스코드 임베드 description 으로 쓸 1~5줄 한국어",
      "blocks": [{"title": "...", "value": "...", "inline": false}, ...],  # 임베드 field 후보
      "cost_krw": 12.34,
      "error": "내부 오류 디버그용 메시지" | null,
    }

핸들러 시그니처는 ``async def handler(payload: dict, user_id: str) -> dict`` 통일.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Callable

from sd_core.utils.errors import ConfigError, SecuDeckError
from sd_core.utils.logger import get_logger


# 봇 핸들러 시그니처. payload 는 cos 가 보낸 자유 dict, user_id 는 디스코드 사용자 ID.
HandlerFn = Callable[..., Awaitable[dict[str, Any]]]


class InternalAPIServer:
    """봇별 1개 띄우는 내부 API 서버.

    사용법::

        api = InternalAPIServer(bot_name="pitch_sharpener")
        api.register("pitch_quick", quick_handler)
        api.register("pitch_review", full_review_handler)

        async with bot:
            await api.start()
            try:
                await bot.start(token)
            finally:
                await api.stop()
    """

    def __init__(
        self,
        bot_name: str,
        *,
        port: int | None = None,
        secret: str | None = None,
        host: str = "0.0.0.0",
    ):
        self.bot_name = bot_name
        # Railway 는 PORT 환경변수를 자동 주입한다. 없으면 INTERNAL_API_PORT, 그 외 8080.
        env_port = os.getenv("PORT") or os.getenv("INTERNAL_API_PORT")
        self.port = int(port if port is not None else (env_port or "8080"))
        self.host = host
        # secret 빈 문자열이면 401 처리하기 위해 환경변수 fallback 명시적 처리
        self.secret = secret if secret is not None else os.getenv("INTERNAL_API_SECRET", "")
        self._handlers: dict[str, HandlerFn] = {}
        # 커스텀 라우트 훅 — argos_self_audit 의 GitHub webhook 처럼
        # /api/invoke 외에 다른 엔드포인트를 같은 포트에 노출하고 싶을 때 사용.
        # `_build_app` 시점에 FastAPI 앱이 인자로 전달된다.
        self._route_hooks: list[Callable[[Any], None]] = []
        self._server: Any | None = None     # uvicorn.Server (런타임에 주입)
        self._task: asyncio.Task | None = None
        self._log = get_logger("sd_core.internal_api", bot_name=bot_name)
        self._app: Any | None = None        # FastAPI 앱 (lazy build)

    # -----------------------------------------------------------------
    # 핸들러 등록
    # -----------------------------------------------------------------
    def register(self, action: str, handler: HandlerFn) -> "InternalAPIServer":
        """``action`` 식별자로 핸들러 등록. 같은 action 재등록은 에러."""
        if action in self._handlers:
            raise ValueError(f"action '{action}' 이미 등록됨")
        self._handlers[action] = handler
        return self

    def add_route_hook(self, hook: Callable[[Any], None]) -> "InternalAPIServer":
        """``_build_app`` 시점에 호출될 콜백 등록.

        ``hook(app)`` 형태로 FastAPI 앱이 전달된다. 호출자는 ``app.add_api_route(...)`` 등으로
        커스텀 엔드포인트를 자유롭게 추가할 수 있다 (예: GitHub webhook 수신).

        주의: 이 훅은 ``/api/invoke`` 의 공유 시크릿 인증을 거치지 않는다.
        외부 시스템(GitHub 등) 으로부터 받는 요청이라면 훅 내부에서 별도 인증을 구현할 것.
        """
        self._route_hooks.append(hook)
        return self

    # -----------------------------------------------------------------
    # FastAPI 앱 빌드 (lazy)
    # -----------------------------------------------------------------
    def _build_app(self) -> Any:
        try:
            from fastapi import FastAPI, Header, HTTPException, Request
        except ImportError as exc:  # noqa: F841
            # 봇 pyproject.toml 에 fastapi 가 빠진 경우. 명확한 한국어 안내.
            raise ConfigError(
                "fastapi 미설치 — 봇 pyproject.toml 의 dependencies 에 "
                "'fastapi>=0.110' 와 'uvicorn>=0.30' 추가 후 'uv sync' 다시 실행해 주세요."
            ) from exc

        app = FastAPI(
            title=f"{self.bot_name} internal API",
            # 운영 봇 노출 최소화 — 외부에서 docs 페이지 노출 안 함.
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )

        bot_name = self.bot_name
        handlers = self._handlers
        secret = self.secret
        log = self._log

        @app.get("/health")
        async def health() -> dict[str, Any]:
            """Railway/uptime 체크용. 인증 없음 — 단, 어떤 데이터도 흘리지 않음."""
            return {
                "status": "ok",
                "bot": bot_name,
                "actions": sorted(handlers.keys()),
            }

        @app.post("/api/invoke")
        async def invoke(
            request: Request,
            x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
        ) -> dict[str, Any]:
            """cos 가 보낸 위임 호출. body 형식: ``{action, user_id, payload}``."""
            # 0. 시크릿 미설정은 운영 사고. 401 이 아니라 503 으로 구분.
            if not secret:
                raise HTTPException(status_code=503, detail="INTERNAL_API_SECRET 미설정")
            # 1. 공유 시크릿 검증
            if x_internal_secret != secret:
                raise HTTPException(status_code=401, detail="shared secret 불일치")

            # 2. 바디 파싱 (Pydantic 의존 회피)
            try:
                body = await request.json()
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=400, detail="JSON body 필요")
            if not isinstance(body, dict):
                raise HTTPException(status_code=400, detail="body 는 객체여야 함")

            action = body.get("action")
            user_id = str(body.get("user_id") or "internal")
            payload = body.get("payload") or {}
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="payload 는 객체여야 함")

            handler = handlers.get(action)
            if handler is None:
                raise HTTPException(status_code=404, detail=f"unknown action: {action}")

            # 3. 핸들러 실행. 도메인 예외는 사용자 친화 메시지로 포장.
            try:
                raw = await handler(payload=payload, user_id=user_id)
            except SecuDeckError as exc:
                log.warning(
                    "invoke_handler_domain_error",
                    action=action,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                return _normalize_result({
                    "ok": False,
                    "summary": exc.user_message,
                    "error": str(exc),
                })
            except Exception as exc:  # noqa: BLE001
                log.exception("invoke_handler_failed", action=action, error=str(exc))
                return _normalize_result({
                    "ok": False,
                    "summary": "내부 오류로 응답을 만들지 못했어요. 잠시 후 다시 시도해 주세요.",
                    "error": str(exc),
                })

            return _normalize_result(raw)

        # 커스텀 라우트 훅 — 호출자 봇이 자유롭게 엔드포인트 추가.
        for hook in self._route_hooks:
            try:
                hook(app)
            except Exception as exc:  # noqa: BLE001 — 훅 자체의 버그는 부팅을 막지 않게 경고만
                self._log.warning("route_hook_failed", error=str(exc))

        return app

    # -----------------------------------------------------------------
    # 라이프사이클
    # -----------------------------------------------------------------
    async def start(self) -> None:
        """uvicorn 서버를 background asyncio task 로 띄움."""
        if self._task is not None:
            return  # 멱등성: 이미 떠 있으면 무시
        if not self._handlers:
            self._log.warning("internal_api_no_handlers", bot=self.bot_name)
        try:
            import uvicorn
        except ImportError as exc:  # noqa: F841
            raise ConfigError(
                "uvicorn 미설치 — 봇 pyproject.toml 의 dependencies 에 "
                "'uvicorn>=0.30' 추가 후 'uv sync' 재실행."
            ) from exc

        self._app = self._build_app()
        config = uvicorn.Config(
            self._app,
            host=self.host,
            port=self.port,
            log_level=os.getenv("UVICORN_LOG_LEVEL", "warning"),
            access_log=False,        # 노이즈 줄이기 (필요 시 환경변수로 켤 수 있게)
            lifespan="off",          # FastAPI 앱에 startup/shutdown 이벤트 없음
        )
        self._server = uvicorn.Server(config)
        # serve() 는 영구 루프이므로 background task 로 실행
        self._task = asyncio.create_task(self._server.serve(), name=f"{self.bot_name}_internal_api")
        self._log.info(
            "internal_api_started",
            port=self.port,
            host=self.host,
            actions=sorted(self._handlers.keys()),
        )

    async def stop(self) -> None:
        """봇 종료 시 우아하게 서버 정지."""
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            except Exception as exc:  # noqa: BLE001
                self._log.warning("internal_api_stop_error", error=str(exc))
        self._task = None
        self._server = None
        self._log.info("internal_api_stopped")


# ---------------------------------------------------------------------
# 결과 정규화 — 봇 핸들러가 반환한 임의 dict 를 cos 가 기대하는 표준형으로 맞춤.
# ---------------------------------------------------------------------
def _normalize_result(raw: Any) -> dict[str, Any]:
    """핸들러 반환값을 ``{ok, summary, blocks, cost_krw, error}`` 로 강제 정규화."""
    if not isinstance(raw, dict):
        return {
            "ok": True,
            "summary": str(raw)[:1500],
            "blocks": [],
            "cost_krw": 0.0,
            "error": None,
        }

    blocks_raw = raw.get("blocks") or []
    blocks: list[dict[str, Any]] = []
    if isinstance(blocks_raw, list):
        for b in blocks_raw:
            if isinstance(b, dict):
                # 임베드 field 호환 키만 추림.
                blocks.append({
                    "title": str(b.get("title", ""))[:256],
                    "value": str(b.get("value", ""))[:1024],
                    "inline": bool(b.get("inline", False)),
                })

    return {
        "ok": bool(raw.get("ok", True)),
        # discord 임베드 description 길이 제한 4096. cos 가 추가 텍스트 붙이므로 여유 있게.
        "summary": str(raw.get("summary", ""))[:3500],
        "blocks": blocks[:20],   # 임베드 field 25개 제한 안전 마진
        "cost_krw": float(raw.get("cost_krw", 0.0) or 0.0),
        "error": raw.get("error"),
    }
