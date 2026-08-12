"""Relevance signals. See enhancements/21.

The reason `99-rejected-alternatives.md` named click-through data as the honest
answer to "how would you fix the sparse-label problem" -- this is the table that
answer stops being hypothetical.
"""

from __future__ import annotations

from typing import Literal
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.db.models import MatchFeedback, User

_OPPOSITE_SIGNAL: dict[str, str] = {"up": "down", "down": "up"}


async def _find(
    db: AsyncSession, user: User, run_id: uuid.UUID | None, job_id: int, signal: str
) -> MatchFeedback | None:
    result = await db.execute(
        select(MatchFeedback).where(
            MatchFeedback.user_id == user.id,
            MatchFeedback.match_run_id == run_id,
            MatchFeedback.job_id == job_id,
            MatchFeedback.signal == signal,
        )
    )
    return result.scalar_one_or_none()


async def submit_feedback(
    db: AsyncSession,
    user: User,
    job_id: int,
    signal: Literal["up", "down", "click"],
    rank: int,
    resume_hash: str,
    run_id: uuid.UUID | None,
) -> tuple[MatchFeedback | None, Literal["created", "removed"]]:
    """Upsert with a toggle: posting the identical `(user, run_id, job_id, signal)`
    twice **removes** the row -- thumbs-up is a toggle, and a UI that can only ever
    add is a UI users cannot correct.

    `up` and `down` are mutually exclusive in both directions: posting either one
    clears any existing row for the *opposite* signal on the same target, not just
    "down clears up" as enhancements/21's own contract sketch states -- a one-way
    override would leave a stale opposite signal any time a user changed their mind
    from down to up, which is not what "mutually exclusive" means. `click` has no
    opposite and only ever toggles against itself.
    """

    existing = await _find(db, user, run_id, job_id, signal)
    if existing is not None:
        await db.delete(existing)
        await db.flush()
        return None, "removed"

    opposite = _OPPOSITE_SIGNAL.get(signal)
    if opposite is not None:
        opposite_row = await _find(db, user, run_id, job_id, opposite)
        if opposite_row is not None:
            await db.delete(opposite_row)
            await db.flush()

    row = MatchFeedback(
        user_id=user.id, match_run_id=run_id, resume_hash=resume_hash, job_id=job_id, signal=signal, rank=rank
    )
    db.add(row)
    await db.flush()
    return row, "created"
