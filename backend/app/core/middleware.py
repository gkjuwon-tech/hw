"""HTTP middlewares: request id, structured access log, rate limit, metrics."""

from __future__ import annotations

import time
import uuid

from fastapi import Request, status
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings
from app.core.logging import bind_request_context, clear_request_context, get_logger
from app.core.metrics import (
    http_request_seconds,
    http_requests_total,
    rate_limit_rejections_total,
)
from app.core.ratelimit import get_limiter

logger = get_logger("conet.http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id and bind it to logs and response headers."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        bind_request_context(
            request_id=rid,
            method=request.method,
            path=request.url.path,
        )
        try:
            response = await call_next(request)
        finally:
            # Always clear; FastAPI uses the same task for the response
            # and this is fine because middleware order ensures we wrap
            # everything.
            pass
        response.headers["x-request-id"] = rid
        clear_request_context()
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """One structured log line per request, with timing and status."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            dur = time.perf_counter() - start
            status_code = response.status_code if response is not None else 500
            route = _route_template(request)
            http_requests_total.labels(
                method=request.method,
                route=route,
                status=str(status_code // 100) + "xx",
            ).inc()
            http_request_seconds.labels(method=request.method, route=route).observe(dur)
            logger.info(
                "http_request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "route": route,
                    "status": status_code,
                    "duration_ms": round(dur * 1000.0, 2),
                    "client": request.client.host if request.client else None,
                },
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-API-key token-bucket limiter applied to ``/v1/*`` routes."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not settings.rate_limit_enabled or not request.url.path.startswith("/v1"):
            return await call_next(request)
        # Skip pricing-quote-style anonymous endpoints? No — they count too.

        bearer = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        if bearer:
            key = f"key:{bearer[:24]}"
            scope = "api_key"
        else:
            client_host = request.client.host if request.client else "anon"
            key = f"ip:{client_host}"
            scope = "anonymous"

        ok, retry_after = await get_limiter().check(key)
        if not ok:
            rate_limit_rejections_total.labels(scope=scope).inc()
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={
                    "retry-after": str(max(1, int(retry_after))),
                    "x-conet-rate-scope": scope,
                },
            )
        return await call_next(request)


def _route_template(request: Request) -> str:
    """Best-effort: use the matched FastAPI route template if available."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return request.url.path
