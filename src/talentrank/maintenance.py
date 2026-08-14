"""Operational maintenance jobs. See enhancements/24.

Pure `AsyncSession`-in, count-out functions -- no HTTP, no scheduling here.
`scripts/maintenance.py` is the CLI entry point; these are never exposed as an
HTTP endpoint and never run as a background task inside the API process, which
would compete with request handling for the one thing this single-worker
service is short of.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.config import get_settings
from src.talentrank.db.models import Session
from src.talentrank.db.types import utcnow


async def purge_expired_sessions(db: AsyncSession, older_than: datetime) -> int:
    """Delete sessions whose `expires_at` has passed, or which were revoked before
    `older_than`. Returns the row count deleted.

    Batched at `settings.session_purge_batch_size` per round trip rather than one
    unbounded `DELETE`, so a large backlog does not hold one long transaction open
    against a table `resolve_session` reads on every authenticated request.
    Idempotent (a second call finds nothing left to delete) and safe to run
    concurrently (each invocation only ever deletes rows it can still see; there is
    no read-then-assume-still-there step).
    """

    settings = get_settings()
    batch_size = settings.session_purge_batch_size
    now = utcnow()
    condition = or_(Session.expires_at <= now, and_(Session.revoked_at.is_not(None), Session.revoked_at < older_than))

    total = 0
    while True:
        stale = await db.execute(select(Session.id).where(condition).limit(batch_size))
        stale_ids = [row[0] for row in stale.all()]
        if not stale_ids:
            break

        await db.execute(delete(Session).where(Session.id.in_(stale_ids)))
        await db.flush()
        total += len(stale_ids)

        if len(stale_ids) < batch_size:
            break

    return total
