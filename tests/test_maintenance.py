"""Tests for src.talentrank.maintenance. See .claude/enhancements/24-operational-hardening.md.

Service-level tests against `db_session` -- no HTTP.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.db.models import Session, User
from src.talentrank.db.types import utcnow
from src.talentrank.maintenance import purge_expired_sessions

pytestmark = pytest.mark.anyio


async def _make_user(db: AsyncSession, email: str) -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


async def _make_session(
    db: AsyncSession,
    user: User,
    *,
    expires_delta: timedelta,
    revoked_delta: timedelta | None = None,
    token_hash: str,
) -> Session:
    now = utcnow()
    session = Session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + expires_delta,
        last_used_at=now,
        revoked_at=(now + revoked_delta) if revoked_delta is not None else None,
    )
    db.add(session)
    await db.flush()
    return session


async def _session_ids(db: AsyncSession) -> set:
    result = await db.execute(select(Session.id))
    return set(result.scalars().all())


async def test_purge_removes_expired_sessions(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "purge-expired@example.com")
    expired = await _make_session(db_session, user, expires_delta=timedelta(days=-1), token_hash="a" * 64)
    live = await _make_session(db_session, user, expires_delta=timedelta(days=1), token_hash="b" * 64)

    deleted = await purge_expired_sessions(db_session, older_than=utcnow() - timedelta(days=30))

    assert deleted == 1
    remaining = await _session_ids(db_session)
    assert remaining == {live.id}
    assert expired.id not in remaining


async def test_purge_keeps_live_sessions(db_session: AsyncSession) -> None:
    """A live, unexpired, never-revoked session must survive regardless of
    `older_than` -- it is not stale, it is in active use."""

    user = await _make_user(db_session, "purge-keeps-live@example.com")
    live = await _make_session(db_session, user, expires_delta=timedelta(days=14), token_hash="c" * 64)
    # Revoked, but recently -- must NOT be purged by a 30-day-old cutoff.
    recently_revoked = await _make_session(
        db_session, user, expires_delta=timedelta(days=14), revoked_delta=timedelta(days=-1), token_hash="d" * 64
    )

    deleted = await purge_expired_sessions(db_session, older_than=utcnow() - timedelta(days=30))

    assert deleted == 0
    remaining = await _session_ids(db_session)
    assert remaining == {live.id, recently_revoked.id}


async def test_purge_is_idempotent(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "purge-idempotent@example.com")
    await _make_session(db_session, user, expires_delta=timedelta(days=-1), token_hash="e" * 64)
    # Revoked well before the cutoff -- should also be purged on the first pass.
    await _make_session(
        db_session, user, expires_delta=timedelta(days=14), revoked_delta=timedelta(days=-60), token_hash="f" * 64
    )

    older_than = utcnow() - timedelta(days=30)
    first = await purge_expired_sessions(db_session, older_than=older_than)
    second = await purge_expired_sessions(db_session, older_than=older_than)

    assert first == 2
    assert second == 0
    assert await _session_ids(db_session) == set()
