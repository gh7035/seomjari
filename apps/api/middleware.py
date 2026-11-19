"""경량 운영 미들웨어: request ID, 레이트리밋, 전역 예외 핸들러."""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from agent.config import settings
from agent.log import get_logger, log_event, set_request_id

log = get_logger("api.mw")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """X-Request-ID를 발급·전파하고 로그 ContextVar에 주입."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        set_request_id(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            dur_ms = (time.perf_counter() - start) * 1000
            log_event(log, 20, "http_request",
                      method=request.method, path=request.url.path,
                      dur_ms=round(dur_ms, 1))
            set_request_id(None)
        response.headers["X-Request-ID"] = rid
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP+버킷별 분당 요청 수 제한.

    버킷
    - read:   /api/map/*, /api/meta, /api/stores  → 읽기 전용. FE가 캐시해도
              MonthTimeline 등은 12연발을 보내므로 상한을 크게 잡는다.
    - write:  /api/diagnose, /api/chat             → LLM/파이프라인 호출. 기본 상한.
    - 기타:   상한의 중간값.
    """

    READ_MULTIPLIER = 10   # read 버킷은 기본 상한의 10배

    def __init__(self, app, limit_per_min: int):
        super().__init__(app)
        self.limit = limit_per_min
        self._lock = threading.Lock()
        self._hits: dict[tuple[str, str], deque[float]] = {}

    def _bucket(self, path: str) -> tuple[str, int]:
        if (path.startswith("/api/map/") or path == "/api/meta"
                or path.startswith("/api/stores") or path == "/api/metrics"):
            return "read", self.limit * self.READ_MULTIPLIER
        if path.startswith("/api/diagnose") or path.startswith("/api/chat"):
            return "write", self.limit
        return "other", max(self.limit, 1)

    async def dispatch(self, request: Request, call_next):
        if self.limit <= 0:
            return await call_next(request)
        path = request.url.path
        if (path.startswith("/livez") or path.startswith("/readyz")
                or path.startswith("/api/health") or not path.startswith("/api/")):
            return await call_next(request)

        bucket, bucket_limit = self._bucket(path)
        client = request.client.host if request.client else "unknown"
        key = (client, bucket)
        now = time.time()
        window = 60.0
        with self._lock:
            dq = self._hits.setdefault(key, deque())
            while dq and now - dq[0] > window:
                dq.popleft()
            if len(dq) >= bucket_limit:
                retry_after = max(1, int(window - (now - dq[0])))
                log_event(log, 30, "rate_limited", ip=client, path=path,
                          bucket=bucket, hits=len(dq), limit=bucket_limit)
                return JSONResponse(
                    {"detail": "rate limit exceeded"},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
            dq.append(now)
        return await call_next(request)


def install(app, enable_cors: bool = True) -> None:
    from fastapi.middleware.cors import CORSMiddleware
    s = settings()
    app.add_middleware(RateLimitMiddleware, limit_per_min=s.rate_limit_per_min)
    app.add_middleware(RequestIdMiddleware)
    if enable_cors and s.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )

    @app.exception_handler(HTTPException)
    async def _http_exc(_, exc: HTTPException):  # noqa: ANN001
        log_event(log, 30, "http_error", status=exc.status_code, detail=str(exc.detail))
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_, exc: Exception):  # noqa: ANN001
        log_event(log, 40, "unhandled_exception",
                  error=type(exc).__name__, msg=str(exc)[:200])
        return JSONResponse(
            {"detail": "internal server error"}, status_code=500,
        )
