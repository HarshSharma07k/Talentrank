"""Tests for the persistence foundation: ORM models, cascades, and the
`get_db` session lifecycle. See .claude/enhancements/19-persistence-foundation.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.talentrank.db.models import MatchFeedback, MatchRun, SavedList, SavedListItem
from src.talentrank.db.models import Session as DBSession
from src.talentrank.db.models import User
from src.talentrank.db.session import get_db
from src.talentrank.db.types import utcnow

pytestmark = pytest.mark.anyio


def _match_run_kwargs(user_id: object) -> dict:
    return {
        "user_id": user_id,
        "label": "run",
        "resume_hash": "a" * 16,
        "resume_text": "resume text",
        "top_k": 30,
        "top_n": 10,
        "filters": {},
        "filters_digest": "a" * 8,
        "results": [],
        "corpus_profile": "demo",
        "took_ms": 1.0,
    }


async def test_tzdatetime_roundtrip_is_utc_aware(db_session: AsyncSession) -> None:
    """The single most important test in this document."""

    non_utc = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
    user = User(email="tz-roundtrip@example.com", password_hash="x", last_login_at=non_utc)
    db_session.add(user)
    await db_session.commit()

    db_session.expire_all()
    fetched = (await db_session.execute(select(User).where(User.email == "tz-roundtrip@example.com"))).scalar_one()

    assert fetched.last_login_at is not None
    assert fetched.last_login_at.tzinfo is timezone.utc
    assert fetched.last_login_at == non_utc  # same instant, regardless of the original offset


async def test_tzdatetime_rejects_naive_datetime(db_session: AsyncSession) -> None:
    user = User(email="tz-naive@example.com", password_hash="x", last_login_at=datetime(2026, 1, 1, 12, 0, 0))
    db_session.add(user)

    with pytest.raises(Exception):
        await db_session.commit()


async def test_user_email_is_unique(db_session: AsyncSession) -> None:
    db_session.add(User(email="dup@example.com", password_hash="x"))
    await db_session.commit()

    db_session.add(User(email="dup@example.com", password_hash="y"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_deleting_user_cascades_to_sessions_and_runs(db_session: AsyncSession) -> None:
    user = User(email="cascade@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    db_session.add(DBSession(user_id=user.id, token_hash="a" * 64, expires_at=utcnow(), last_used_at=utcnow()))
    db_session.add(MatchRun(**_match_run_kwargs(user.id)))
    await db_session.commit()

    # A Core-style bulk delete, deliberately not `await db_session.delete(user)` --
    # a bulk delete bypasses the ORM's own `relationship(cascade=...)` machinery
    # entirely, so this proves `PRAGMA foreign_keys=ON` is actually wired at the DB
    # level. The ORM-level cascade would mask a missing pragma in any test that
    # went through `Session.delete()` instead.
    await db_session.execute(delete(User).where(User.id == user.id))
    await db_session.commit()

    remaining_sessions = (await db_session.execute(select(DBSession))).scalars().all()
    remaining_runs = (await db_session.execute(select(MatchRun))).scalars().all()
    assert remaining_sessions == []
    assert remaining_runs == []


async def test_saved_list_item_unique_per_list(db_session: AsyncSession) -> None:
    user = User(email="lists@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    saved_list = SavedList(user_id=user.id, name="Shortlist")
    db_session.add(saved_list)
    await db_session.flush()

    item_kwargs = {"saved_list_id": saved_list.id, "job_id": 1, "job_title": "Engineer", "job_family": "ENGINEERING"}
    db_session.add(SavedListItem(**item_kwargs))
    await db_session.commit()

    db_session.add(SavedListItem(**item_kwargs))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_match_feedback_signal_is_idempotent(db_session: AsyncSession) -> None:
    user = User(email="feedback@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    # `match_run_id` must be a real row here, not None: it is nullable, and SQL's
    # unique-constraint semantics never treat two NULLs as equal, so a constraint
    # spanning a nullable column silently allows unlimited duplicates with NULL in
    # that slot. Idempotency only holds for feedback tied to a persisted run.
    run = MatchRun(**_match_run_kwargs(user.id))
    db_session.add(run)
    await db_session.flush()

    signal_kwargs = {
        "user_id": user.id,
        "match_run_id": run.id,
        "resume_hash": "a" * 16,
        "job_id": 1,
        "signal": "up",
        "rank": 1,
    }
    db_session.add(MatchFeedback(**signal_kwargs))
    await db_session.commit()

    db_session.add(MatchFeedback(**signal_kwargs))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_get_db_rolls_back_on_exception(db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("src.talentrank.db.session.get_sessionmaker", lambda: sessionmaker)

    with pytest.raises(RuntimeError, match="boom"):
        async for session in get_db():
            session.add(User(email="rollback@example.com", password_hash="x"))
            raise RuntimeError("boom")

    async with sessionmaker() as verify_session:
        rows = (await verify_session.execute(select(User))).scalars().all()
    assert rows == []


async def test_sessionmaker_does_not_expire_on_commit(db_session: AsyncSession) -> None:
    user = User(email="expire@example.com", password_hash="x")
    db_session.add(user)
    await db_session.commit()

    # Attribute access after commit must not raise MissingGreenlet.
    assert user.email == "expire@example.com"
