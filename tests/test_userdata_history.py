"""Tests for match-run persistence, listing, and import. See
.claude/enhancements/21-user-scoped-data.md.

Service-level tests against `db_session` -- no HTTP. HTTP-level ownership tests
(404 vs 403) live in `test_userdata_api.py`, once `/me/*` routes exist to test.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.config import get_settings
from src.talentrank.db.models import User
from src.talentrank.schemas import JobMatch, MatchFilters, MatchRequest, MatchResponse, ScoreBreakdown
from src.talentrank.userdata import history
from src.talentrank.userdata.schemas import ImportEntry

pytestmark = pytest.mark.anyio


def _job_match(job_id: int, description: str = "short description") -> JobMatch:
    return JobMatch(
        job_id=job_id,
        job_title=f"Job {job_id}",
        description=description,
        skills="",
        job_category="JOB",
        job_family="OTHER",
        bi_encoder_score=0.5,
        cross_encoder_score=0.5,
        scores=ScoreBreakdown(bi_encoder=0.5, cross_encoder=0.5, cross_encoder_probability=0.6, skill_overlap=0.0),
        explanation=None,
        retrieval_rank=1,
        rank=1,
    )


def _match_response(n_results: int = 1, description: str = "short description") -> MatchResponse:
    results = [_job_match(i, description) for i in range(1, n_results + 1)]
    return MatchResponse(
        results=results,
        stage="rerank",
        top_k=30,
        top_n=10,
        total_candidates=n_results,
        filtered_candidates=n_results,
        took_ms=12.3,
        cached=False,
        corpus_size=100,
        resume_hash="a" * 16,
        run_id=None,
    )


def _match_request(resume_text: str = "x" * 60) -> MatchRequest:
    return MatchRequest(resume_text=resume_text, top_k=30, top_n=10, filters=MatchFilters(), explain=False)


async def _make_user(db: AsyncSession, email: str) -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


async def test_history_is_scoped_to_owner(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "owner@example.com")
    other = await _make_user(db_session, "other@example.com")

    run_id = await history.persist_run(db_session, owner, _match_request(), _match_response())
    assert run_id is not None

    import uuid

    assert await history.get_run(db_session, other, uuid.UUID(run_id)) is None
    assert await history.rename_run(db_session, other, uuid.UUID(run_id), "renamed") is None
    assert await history.delete_run(db_session, other, uuid.UUID(run_id)) is False

    # The owner can still do all three.
    assert await history.get_run(db_session, owner, uuid.UUID(run_id)) is not None


async def test_history_list_is_ordered_newest_first(db_session: AsyncSession) -> None:
    """`list_runs` itself returns full ORM rows (`.results` intact) -- omitting
    `results` from the wire response is the router/schema's job, built from these
    rows without ever reading `.results` into `MatchRunSummary`. See
    `test_userdata_api.py::test_history_list_omits_results_payload` for the actual
    HTTP-level guarantee the doc requires.
    """

    user = await _make_user(db_session, "lister@example.com")
    first_id = await history.persist_run(
        db_session, user, _match_request("first" + "x" * 60), _match_response(n_results=5)
    )
    second_id = await history.persist_run(db_session, user, _match_request("second" + "x" * 60), _match_response())

    rows = await history.list_runs(db_session, user, page=1, page_size=20)

    assert len(rows) == 2
    assert str(rows[0].id) == second_id  # newest first
    assert str(rows[1].id) == first_id
    assert len(rows[1].results) == 5


async def test_history_drops_oldest_beyond_quota(db_session: AsyncSession) -> None:
    settings = get_settings()
    settings.max_history_entries_per_user = 3

    user = await _make_user(db_session, "quota@example.com")
    for i in range(5):
        await history.persist_run(db_session, user, _match_request(f"resume-{i}" + "x" * 60), _match_response())

    rows = await history.list_runs(db_session, user, page=1, page_size=20)
    assert len(rows) == 3


async def test_persist_run_clips_descriptions(db_session: AsyncSession) -> None:
    settings = get_settings()
    settings.history_description_max_chars = 10

    user = await _make_user(db_session, "clip@example.com")
    long_description = "y" * 500
    run_id = await history.persist_run(
        db_session, user, _match_request(), _match_response(description=long_description)
    )
    assert run_id is not None

    import uuid

    row = await history.get_run(db_session, user, uuid.UUID(run_id))
    assert row is not None
    assert len(row.results[0]["description"]) == 10


async def test_import_dedups_on_resume_hash_and_settings(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "importdedup@example.com")
    resume_text = "z" * 80

    entries = [
        ImportEntry(
            created_at=1_700_000_000_000,
            label="first",
            resume_text=resume_text,
            top_k=30,
            top_n=10,
            filters=MatchFilters(),
            results=[_job_match(1)],
        ),
        ImportEntry(
            created_at=1_700_000_100_000,
            label="second (same resume/settings)",
            resume_text=resume_text,
            top_k=30,
            top_n=10,
            filters=MatchFilters(),
            results=[_job_match(1)],
        ),
    ]

    result = await history.import_entries(db_session, user, entries)

    assert result.imported == 1
    assert result.skipped_duplicate == 1
    rows = await history.list_runs(db_session, user, page=1, page_size=20)
    assert len(rows) == 1


async def test_import_keeps_earliest_created_at(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "importearliest@example.com")
    resume_text = "w" * 80
    later = 1_700_000_100_000
    earlier = 1_700_000_000_000

    await history.import_entries(
        db_session,
        user,
        [
            ImportEntry(
                created_at=later,
                label="later",
                resume_text=resume_text,
                top_k=30,
                top_n=10,
                filters=MatchFilters(),
                results=[_job_match(1)],
            )
        ],
    )
    await history.import_entries(
        db_session,
        user,
        [
            ImportEntry(
                created_at=earlier,
                label="earlier",
                resume_text=resume_text,
                top_k=30,
                top_n=10,
                filters=MatchFilters(),
                results=[_job_match(1)],
            )
        ],
    )

    rows = await history.list_runs(db_session, user, page=1, page_size=20)
    assert len(rows) == 1
    assert rows[0].created_at.timestamp() * 1000 == pytest.approx(earlier, abs=1)


async def test_import_is_idempotent(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "importidempotent@example.com")
    entries = [
        ImportEntry(
            created_at=1_700_000_000_000,
            label="one",
            resume_text="v" * 80,
            top_k=30,
            top_n=10,
            filters=MatchFilters(),
            results=[_job_match(1)],
        )
    ]

    first = await history.import_entries(db_session, user, entries)
    second = await history.import_entries(db_session, user, entries)

    assert first.imported == 1
    assert second.imported == 0
    assert second.skipped_duplicate == 1
    rows = await history.list_runs(db_session, user, page=1, page_size=20)
    assert len(rows) == 1


async def test_import_respects_quota(db_session: AsyncSession) -> None:
    settings = get_settings()
    settings.max_history_entries_per_user = 2

    user = await _make_user(db_session, "importquota@example.com")
    entries = [
        ImportEntry(
            created_at=1_700_000_000_000 + i,
            label=f"entry-{i}",
            resume_text=f"u{i}" * 40,
            top_k=30,
            top_n=10,
            filters=MatchFilters(),
            results=[_job_match(1)],
        )
        for i in range(5)
    ]

    result = await history.import_entries(db_session, user, entries)

    assert result.imported == 5
    assert result.skipped_quota == 3
    rows = await history.list_runs(db_session, user, page=1, page_size=20)
    assert len(rows) == 2
