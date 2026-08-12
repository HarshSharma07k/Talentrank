"""HTTP middleware for TalentRank: request-id/timing logging and IP rate limiting.
See enhancements/07.

Both middlewares are `BaseHTTPMiddleware` subclasses, registered in `api.py`. Order
matters: `CORSMiddleware` must be added *after* these (making it the outermost layer)
so CORS headers still land on a 429 or 503 response, not just a 200.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import hashlib
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


def _consume_rate_limit_token(key: str, capacity: int, window_seconds: int) -> bool:
    """Shared token-bucket check-and-consume, backed by `get_cache_backend()`.

    Returns `True` (and persists the decremented bucket) when the request is
    allowed, `False` when the caller should be rejected. Factored out of
    `RateLimitMiddleware` so `auth.deps.auth_rate_limiter` (enhancements/20) reuses
    the exact same algorithm against a different key/capacity rather than
    reimplementing it -- a FastAPI dependency raises `HTTPException` instead of
    returning a `Response`, so the two call sites can't share the wrapping code,
    only this core.
    """

    cache = get_cache_backend()
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
        return False
    tokens -= 1.0

    try:
        cache.set(key, json.dumps({"tokens": tokens, "last": now}).encode("utf-8"), ttl_seconds=window_seconds * 2)
    except Exception:
        pass

    return True


def _bearer_token(request: Request) -> str | None:
    """The raw bearer token from `Authorization`, or `None` if the header is absent
    or not a well-formed `Bearer <token>` value. Never validates the token itself --
    that is `auth.service.resolve_session`'s job, not the rate limiter's."""

    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limiter backed by the same `InMemoryTTLCache` used for
    match results. ~20 lines by design -- `slowapi` is not justified for one bucket
    algorithm on a single-process demo API.

    Buckets on the caller's identity when it's cheaply knowable, IP otherwise:
    a request carrying a well-formed `Authorization: Bearer <token>` header buckets
    on `ratelimit:v1:tok:{sha256(token)[:16]}` at the more generous
    `authenticated_rate_limit_requests`, since `BaseHTTPMiddleware` runs before
    FastAPI resolves any dependency and so cannot afford a DB lookup to find out who
    the caller actually is (enhancements/20). An invalid or expired token still gets
    the generous bucket -- acceptable, because such a request 401s at the dependency
    having done no model inference, and the alternative (a DB lookup in middleware
    on every anonymous request too) is a much worse trade.
    """

    async def dispatch(self, request: Request, call_next: _Call) -> Response:
        settings = get_settings()
        token = _bearer_token(request)

        if token is not None:
            token_fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
            key = f"ratelimit:v1:tok:{token_fingerprint}"
            capacity = settings.authenticated_rate_limit_requests
        else:
            key = f"ratelimit:v1:{_client_ip(request)}"
            capacity = settings.rate_limit_requests
        window_seconds = settings.rate_limit_window_seconds

        if not _consume_rate_limit_token(key, capacity, window_seconds):
            return Response(
                content=json.dumps({"detail": "Rate limit exceeded, please slow down."}),
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(window_seconds)},
            )

        return await call_next(request)
