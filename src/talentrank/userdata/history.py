"""Match-run persistence, listing, and localStorage import. See enhancements/21."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.config import Settings, get_settings
from src.talentrank.db.models import MatchRun
from src.talentrank.db.models import User
from src.talentrank.pipeline import _filters_digest, resume_digest
from src.talentrank.schemas import JobMatch, MatchRequest, MatchResponse
from src.talentrank.userdata.schemas import ImportEntry, ImportResult

logger = logging.getLogger("talentrank.userdata")


def _clip_result(result: JobMatch, settings: Settings) -> dict:
    """A `JobMatch`, dumped to a JSON-safe dict with its description clipped to
    `settings.history_description_max_chars` before storage -- descriptions
    average several thousand characters, and twenty runs of ten results each is
    otherwise megabytes of JSON per user, for text the history view truncates
    anyway.
    """

    payload = result.model_dump(mode="json")
    payload["description"] = str(payload.get("description", ""))[: settings.history_description_max_chars]
    return payload


def _derive_label(resume_text: str, settings: Settings) -> str:
    """Mirrors `frontend/src/lib/history.ts`'s `makeLabel`, so a run auto-labelled
    server-side looks the same as one auto-labelled client-side."""

    trimmed = " ".join(resume_text.split())
    max_chars = settings.history_label_max_chars
    if len(trimmed) > max_chars:
        return f"{trimmed[:max_chars].rstrip()}…"
    return trimmed


async def _enforce_history_quota(db: AsyncSession, user: User) -> int:
    """Deletes the user's oldest `match_runs` rows beyond
    `settings.max_history_entries_per_user`. Returns the number deleted.

    History is a rolling window, not something the user explicitly created --
    breach means drop the oldest, silently, never a 409 (contrast `lists.py`'s
    quota, which does 409: the user named that thing).
    """

    settings = get_settings()
    total = (
        await db.execute(select(func.count()).select_from(MatchRun).where(MatchRun.user_id == user.id))
    ).scalar_one()
    overflow = total - settings.max_history_entries_per_user
    if overflow <= 0:
        return 0

    stale = await db.execute(
        select(MatchRun.id).where(MatchRun.user_id == user.id).order_by(MatchRun.created_at.asc()).limit(overflow)
    )
    stale_ids = [row[0] for row in stale.all()]
    if stale_ids:
        await db.execute(delete(MatchRun).where(MatchRun.id.in_(stale_ids)))
        await db.flush()
    return len(stale_ids)


async def persist_run(db: AsyncSession, user: User, request: MatchRequest, response: MatchResponse) -> str | None:
    """Store a `match_runs` row and return its id, or None on any failure.

    Wrapped in try/except by design, mirroring how `cached_match` guards its own
    cache calls: a persistence outage degrades the product to "history didn't
    save", never to a 500 on the core feature. Logs at warning, rolls back, and
    returns None -- the caller (`api.match_resume`) treats that exactly like an
    anonymous request, leaving `MatchResponse.run_id` at `None`.
    """

    try:
        settings = get_settings()
        row = MatchRun(
            user_id=user.id,
            label=_derive_label(request.resume_text, settings),
            resume_hash=response.resume_hash,
            resume_text=request.resume_text,
            top_k=response.top_k,
            top_n=response.top_n,
            filters=request.filters.model_dump(mode="json"),
            filters_digest=_filters_digest(request.filters),
            results=[_clip_result(r, settings) for r in response.results],
            corpus_profile=settings.corpus_profile,
            took_ms=response.took_ms,
        )
        db.add(row)
        await db.flush()
        await _enforce_history_quota(db, user)
        return str(row.id)
    except Exception:
        logger.warning("persist_run failed; history not saved for this request.", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            logger.debug("Rollback after a failed persist_run also failed; session is likely unusable.")
        return None


async def list_runs(db: AsyncSession, user: User, page: int, page_size: int) -> list[MatchRun]:
    result = await db.execute(
        select(MatchRun)
        .where(MatchRun.user_id == user.id)
        .order_by(MatchRun.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all())


async def get_run(db: AsyncSession, user: User, run_id: uuid.UUID) -> MatchRun | None:
    """Ownership is enforced in the query, not after it -- see enhancements/21's own
    note on why. A row belonging to another user must be indistinguishable from a
    row that does not exist.
    """

    result = await db.execute(select(MatchRun).where(MatchRun.id == run_id, MatchRun.user_id == user.id))
    return result.scalar_one_or_none()


async def rename_run(db: AsyncSession, user: User, run_id: uuid.UUID, label: str) -> MatchRun | None:
    row = await get_run(db, user, run_id)
    if row is None:
        return None
    row.label = label
    await db.flush()
    return row


async def delete_run(db: AsyncSession, user: User, run_id: uuid.UUID) -> bool:
    result = await db.execute(delete(MatchRun).where(MatchRun.id == run_id, MatchRun.user_id == user.id))
    return result.rowcount > 0


async def clear_runs(db: AsyncSession, user: User) -> int:
    result = await db.execute(delete(MatchRun).where(MatchRun.user_id == user.id))
    return result.rowcount


async def import_entries(db: AsyncSession, user: User, entries: list[ImportEntry]) -> ImportResult:
    """The `enhancements/23` migration path: bulk-imports `localStorage` history
    entries, deduplicating against both the user's existing rows and other entries
    in the same batch on `(resume_hash, top_k, top_n, filters_digest)` -- the same
    tuple that already identifies "the same run" everywhere else in this codebase.
    A duplicate keeps the earlier of its two `created_at` values rather than being
    silently dropped, so importing does not lose real chronological history.
    """

    settings = get_settings()

    existing_rows = (await db.execute(select(MatchRun).where(MatchRun.user_id == user.id))).scalars().all()
    key_index: dict[tuple[str, int, int, str], MatchRun] = {
        (row.resume_hash, row.top_k, row.top_n, row.filters_digest): row for row in existing_rows
    }

    imported = 0
    skipped_duplicate = 0

    for entry in entries:
        digest = resume_digest(entry.resume_text)
        filters_digest_value = _filters_digest(entry.filters)
        key = (digest, entry.top_k, entry.top_n, filters_digest_value)
        created_at = datetime.fromtimestamp(entry.created_at / 1000, tz=timezone.utc)

        existing = key_index.get(key)
        if existing is not None:
            if created_at < existing.created_at:
                existing.created_at = created_at
            skipped_duplicate += 1
            continue

        row = MatchRun(
            user_id=user.id,
            label=entry.label,
            resume_hash=digest,
            resume_text=entry.resume_text,
            top_k=entry.top_k,
            top_n=entry.top_n,
            filters=entry.filters.model_dump(mode="json"),
            filters_digest=filters_digest_value,
            results=[_clip_result(r, settings) for r in entry.results],
            corpus_profile=settings.corpus_profile,
            took_ms=0.0,
            created_at=created_at,
        )
        db.add(row)
        key_index[key] = row
        imported += 1

    await db.flush()
    skipped_quota = await _enforce_history_quota(db, user)

    return ImportResult(imported=imported, skipped_duplicate=skipped_duplicate, skipped_quota=skipped_quota)
