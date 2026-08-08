"""HTTP middleware for TalentRank: request-id/timing logging and IP rate limiting.
See enhancements/07.

Both middlewares are `BaseHTTPMiddleware` subclasses, registered in `api.py`. Order
matters: `CORSMiddleware` must be added *after* these (making it the outermost layer)
so CORS headers still land on a 429 or 503 response, not just a 200.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.talentrank.cache import get_cache_backend
from src.talentrank.config import get_settings

logger = logging.getLogger("talentrank.request")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

_Call = Callable[[Request], Awaitable[Response]]


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Stamps `X-Request-ID` / `X-Process-Time-Ms` and logs one structured line per
    request via stdlib `logging`. Deliberately not `structlog` -- one JSON line is
    all a single-process demo API needs."""

    async def dispatch(self, request: Request, call_next: _Call) -> Response:
        request_id = uuid.uuid4().hex[:8]
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
        logger.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "took_ms": round(elapsed_ms, 1),
                }
            )
        )
        return response


def _client_ip(request: Request) -> str:
    """Best-effort client IP for rate-limit bucketing. Reads `X-Forwarded-For` for
    the Hugging Face proxy, but this header is never to be trusted for anything
    security-relevant -- a client can set it to whatever it wants."""

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP token-bucket rate limiter backed by the same `InMemoryTTLCache` used for
    match results. ~40 lines by design -- `slowapi` is not justified for one bucket
    algorithm on a single-process demo API.
    """

    async def dispatch(self, request: Request, call_next: _Call) -> Response:
        settings = get_settings()
        cache = get_cache_backend()
        ip = _client_ip(request)
        key = f"ratelimit:v1:{ip}"
        capacity = settings.rate_limit_requests
        window_seconds = settings.rate_limit_window_seconds
        refill_rate = capacity / window_seconds
        now = time.monotonic()

        try:
            raw = cache.get(key)
        except Exception:
            raw = None

        if raw is None:
            tokens = float(capacity)
        else:
            state = json.loads(raw)
            tokens = min(float(capacity), state["tokens"] + (now - state["last"]) * refill_rate)

        if tokens < 1.0:
            return Response(
                content=json.dumps({"detail": "Rate limit exceeded, please slow down."}),
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(window_seconds)},
            )
        tokens -= 1.0

        try:
            cache.set(key, json.dumps({"tokens": tokens, "last": now}).encode("utf-8"), ttl_seconds=window_seconds * 2)
        except Exception:
            pass

        return await call_next(request)
