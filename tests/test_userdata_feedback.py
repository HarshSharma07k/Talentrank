"""Tests for relevance feedback. See .claude/enhancements/21-user-scoped-data.md.

Service-level tests against `db_session` -- no HTTP.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.db.models import User
from src.talentrank.userdata import feedback
from src.talentrank.userdata.schemas import FeedbackRequest

pytestmark = pytest.mark.anyio


async def _make_user(db: AsyncSession, email: str) -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


async def test_feedback_upsert_toggles_off(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "toggle@example.com")

    row, action = await feedback.submit_feedback(
        db_session, user, job_id=1, signal="up", rank=1, resume_hash="a" * 16, run_id=None
    )
    assert action == "created"
    assert row is not None

    row2, action2 = await feedback.submit_feedback(
        db_session, user, job_id=1, signal="up", rank=1, resume_hash="a" * 16, run_id=None
    )
    assert action2 == "removed"
    assert row2 is None


async def test_up_replaces_down(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "up-down@example.com")

    await feedback.submit_feedback(db_session, user, job_id=1, signal="down", rank=1, resume_hash="a" * 16, run_id=None)
    row, action = await feedback.submit_feedback(
        db_session, user, job_id=1, signal="up", rank=1, resume_hash="a" * 16, run_id=None
    )

    assert action == "created"
    assert row is not None
    assert row.signal == "up"

    # The opposite (down) row must be gone, not just superseded.
    down_row, down_action = await feedback.submit_feedback(
        db_session, user, job_id=1, signal="down", rank=1, resume_hash="a" * 16, run_id=None
    )
    assert down_action == "created"  # would be "removed" if the old down row had survived
    assert down_row is not None


async def test_feedback_requires_rank() -> None:
    with pytest.raises(ValidationError):
        FeedbackRequest(job_id=1, signal="up", resume_hash="a" * 16)  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        FeedbackRequest(job_id=1, signal="up", rank=0, resume_hash="a" * 16)  # rank must be >= 1


async def test_feedback_scoped_to_owner(db_session: AsyncSession) -> None:
    user_a = await _make_user(db_session, "feedback-a@example.com")
    user_b = await _make_user(db_session, "feedback-b@example.com")

    row_a, action_a = await feedback.submit_feedback(
        db_session, user_a, job_id=1, signal="up", rank=1, resume_hash="a" * 16, run_id=None
    )
    row_b, action_b = await feedback.submit_feedback(
        db_session, user_b, job_id=1, signal="up", rank=1, resume_hash="a" * 16, run_id=None
    )

    # Both created independently -- B's post did not toggle off A's row.
    assert action_a == "created"
    assert action_b == "created"
    assert row_a is not None and row_b is not None
    assert row_a.id != row_b.id


async def test_feedback_accepts_null_run_id(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "null-run@example.com")

    row, action = await feedback.submit_feedback(
        db_session, user, job_id=1, signal="click", rank=3, resume_hash="a" * 16, run_id=None
    )

    assert action == "created"
    assert row is not None
    assert row.match_run_id is None
