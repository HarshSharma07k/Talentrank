"""FastAPI dependencies for authentication. See enhancements/20 and /21."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.auth import service
from src.talentrank.config import get_settings
from src.talentrank.db.models import User
from src.talentrank.db.session import get_db
from src.talentrank.middleware import _client_ip, _consume_rate_limit_token

logger = logging.getLogger("talentrank.auth")

_bearer = HTTPBearer(auto_error=False)  # auto_error=False: anonymous is valid, not a 403


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User | None:
    """Resolve the bearer token to a user, or None. **Never raises.** A missing,
    malformed, expired, or revoked token all yield None -- endpoints that are public
    for anonymous callers must not start 401-ing because someone sent a stale
    token.

    Deliberately does **not** declare `Depends(get_db)`: FastAPI resolves every
    declared dependency unconditionally, before this function's own body ever runs
    -- so a `db` parameter here would put a database session on the critical path
    of *every* caller, including a fully anonymous one with no `Authorization`
    header at all. That is exactly the risk enhancements/21 flags explicitly for
    its own first real use of this dependency (`/match`, a public endpoint that
    must keep working with the database down): "either make the dependency
    tolerant, or scope the DB dependency so an anonymous request never needs a
    connection." This opens a session only when a bearer token is actually
    present -- so an anonymous request structurally never enters `get_db`'s code
    path at all, not merely "enters it harmlessly."

    Drives `get_db` manually via `contextlib.asynccontextmanager` rather than
    `Depends(get_db)`, but still looks it up through
    `request.app.dependency_overrides` first -- so it still resolves to whatever a
    test's `app.dependency_overrides[get_db] = ...` installed, exactly as if it had
    been a normal `Depends()`. Calling `get_sessionmaker()` directly instead would
    silently bypass that override and hit the real, unmigrated production database
    in every test -- a real failure caught while building this document's own
    tests (`OperationalError: no such table: sessions`).
    """

    if credentials is None:
        return None

    db_dependency = request.app.dependency_overrides.get(get_db, get_db)
    try:
        async with asynccontextmanager(db_dependency)() as db:
            return await service.resolve_session(db, credentials.credentials)
    except Exception:
        logger.warning("Could not resolve session; treating the request as anonymous.", exc_info=True)
        return None


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
