"""FastAPI dependencies for authentication. See enhancements/20."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.auth import service
from src.talentrank.config import get_settings
from src.talentrank.db.models import User
from src.talentrank.db.session import get_db
from src.talentrank.middleware import _client_ip, _consume_rate_limit_token

_bearer = HTTPBearer(auto_error=False)  # auto_error=False: anonymous is valid, not a 403


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Resolve the bearer token to a user, or None. **Never raises.** A missing,
    malformed, expired, or revoked token all yield None -- endpoints that are public
    for anonymous callers must not start 401-ing because someone sent a stale
    token.
    """

    if credentials is None:
        return None
    return await service.resolve_session(db, credentials.credentials)


async def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    """401 with `WWW-Authenticate: Bearer` when `get_optional_user` yielded None."""

    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.", headers={"WWW-Authenticate": "Bearer"})
    return user


async def get_current_user_and_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, str]:
    """Like `get_current_user`, but also returns the raw bearer token -- for the
    handful of endpoints (`logout`, `change-password`) that need to identify *this*
    session specifically, not just the calling user. Not in enhancements/20's own
    contract sketch, which never explains how `change_password` is supposed to know
    which session is "the caller's own" -- added as part of this document's work.
    """

    if credentials is not None:
        user = await service.resolve_session(db, credentials.credentials)
        if user is not None:
            return user, credentials.credentials
    raise HTTPException(status_code=401, detail="Not authenticated.", headers={"WWW-Authenticate": "Bearer"})


async def auth_rate_limiter(request: Request) -> None:
    """Strict per-IP limiter for `/auth/*` only, applied as a router dependency
    rather than middleware so it is scoped precisely to the credential endpoints.
    Same token bucket and same `get_cache_backend()` as
    `middleware.RateLimitMiddleware` (via the shared `_consume_rate_limit_token`),
    but keyed `authlimit:v1:{ip}` at `auth_rate_limit_requests` per
    `auth_rate_limit_window_seconds`. 429 with `Retry-After`.
    """

    settings = get_settings()
    key = f"authlimit:v1:{_client_ip(request)}"
    window_seconds = settings.auth_rate_limit_window_seconds

    if not _consume_rate_limit_token(key, settings.auth_rate_limit_requests, window_seconds):
        raise HTTPException(
            status_code=429,
            detail="Too many authentication attempts, please slow down.",
            headers={"Retry-After": str(window_seconds)},
        )
