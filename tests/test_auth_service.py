"""Tests for the auth service layer. See .claude/enhancements/20-authentication-backend.md.

Pure-service tests against the `db_session` fixture from enhancements/19 -- no HTTP.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.auth import service
from src.talentrank.auth.passwords import DUMMY_HASH, hash_password
from src.talentrank.config import get_settings
from src.talentrank.db.models import Session as DBSession
from src.talentrank.db.models import User
from src.talentrank.db.types import utcnow

pytestmark = pytest.mark.anyio


async def _make_user(
    db: AsyncSession, email: str = "user@example.com", password: str = "correct-horse-battery"
) -> User:
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    await db.flush()
    return user


async def test_register_lowercases_email(db_session: AsyncSession) -> None:
    user = await service.register_user(db_session, "MixedCase@Example.com", "correct-horse-battery")

    assert user.email == "mixedcase@example.com"


async def test_register_duplicate_email_raises(db_session: AsyncSession) -> None:
    await service.register_user(db_session, "dup@example.com", "correct-horse-battery")

    with pytest.raises(service.EmailAlreadyRegisteredError):
        await service.register_user(db_session, "DUP@example.com", "another-password")


async def test_authenticate_returns_none_for_unknown_email(db_session: AsyncSession) -> None:
    result = await service.authenticate(db_session, "nobody@example.com", "whatever-password")

    assert result is None


async def test_authenticate_verifies_dummy_hash_when_user_absent(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    original_verify = service.verify_password

    def spy(password_hash: str, password: str) -> bool:
        calls.append((password_hash, password))
        return original_verify(password_hash, password)

    monkeypatch.setattr(service, "verify_password", spy)

    result = await service.authenticate(db_session, "nobody@example.com", "whatever-password")

    assert result is None
    assert calls == [(DUMMY_HASH, "whatever-password")]


async def test_authenticate_rehashes_stale_hash(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    settings.argon2_time_cost = 1
    settings.argon2_memory_cost_kib = 8
    from src.talentrank.auth.passwords import get_password_hasher

    get_password_hasher.cache_clear()

    user = await _make_user(db_session, password="correct-horse-battery")
    weak_hash = user.password_hash

    settings.argon2_time_cost = 2
    settings.argon2_memory_cost_kib = 19456
    get_password_hasher.cache_clear()

    authenticated = await service.authenticate(db_session, user.email, "correct-horse-battery")

    assert authenticated is not None
    assert authenticated.password_hash != weak_hash
    # The old password still works against the freshly rehashed value.
    assert await service.authenticate(db_session, user.email, "correct-horse-battery") is not None


async def test_resolve_session_rejects_expired(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    token, session_row = await service.create_session(db_session, user, user_agent=None)
    session_row.expires_at = utcnow()
    await db_session.flush()

    assert await service.resolve_session(db_session, token) is None


async def test_resolve_session_rejects_revoked(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    token, _session_row = await service.create_session(db_session, user, user_agent=None)
    await service.revoke_session(db_session, token)

    assert await service.resolve_session(db_session, token) is None


async def test_resolve_session_rejects_inactive_user(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    token, _session_row = await service.create_session(db_session, user, user_agent=None)
    user.is_active = False
    await db_session.flush()

    assert await service.resolve_session(db_session, token) is None


async def test_resolve_session_does_not_write_within_renewal_window(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    token, session_row = await service.create_session(db_session, user, user_agent=None)
    original_expires_at = session_row.expires_at
    original_last_used_at = session_row.last_used_at

    resolved = await service.resolve_session(db_session, token)

    assert resolved is not None
    assert session_row.expires_at == original_expires_at
    assert session_row.last_used_at == original_last_used_at


async def test_create_session_prunes_beyond_max_per_user(db_session: AsyncSession) -> None:
    settings = get_settings()
    settings.session_max_per_user = 2

    user = await _make_user(db_session)
    for _ in range(4):
        await service.create_session(db_session, user, user_agent=None)

    rows = (await db_session.execute(select(DBSession).where(DBSession.user_id == user.id))).scalars().all()
    assert len(rows) == 2


async def test_change_password_revokes_other_sessions_but_not_caller(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, password="old-password-1234")
    caller_token, _ = await service.create_session(db_session, user, user_agent=None)
    other_token, _ = await service.create_session(db_session, user, user_agent=None)

    await service.change_password(db_session, user, "old-password-1234", "new-password-5678", caller_token)

    assert await service.resolve_session(db_session, caller_token) is not None
    assert await service.resolve_session(db_session, other_token) is None


async def test_change_password_wrong_current_raises(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, password="old-password-1234")
    token, _ = await service.create_session(db_session, user, user_agent=None)

    with pytest.raises(service.InvalidCurrentPasswordError):
        await service.change_password(db_session, user, "totally-wrong", "new-password-5678", token)


async def test_session_row_never_stores_plaintext_token(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    token, session_row = await service.create_session(db_session, user, user_agent=None)

    for column in DBSession.__table__.columns:
        value = getattr(session_row, column.name)
        assert token != value
        if isinstance(value, str):
            assert token not in value
