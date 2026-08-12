"""Request/response models for the `/me` router. See enhancements/21."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.talentrank.schemas import JobMatch, MatchFilters


# --- History -----------------------------------------------------------------


class MatchRunSummary(BaseModel):
    """One row of `GET /me/history`. Deliberately omits `results` -- a list view
    that eagerly serialises twenty runs x ten stored results is a slow endpoint
    and a large response for data the list does not render."""

    id: str
    label: str
    created_at: datetime
    top_k: int
    top_n: int
    filters: MatchFilters
    corpus_profile: str
    result_count: int
    top_job_titles: list[str]  # the first three, for a preview line


class MatchRunDetail(BaseModel):
    """`GET /me/history/{run_id}`. The full stored payload."""

    id: str
    label: str
    resume_hash: str
    resume_text: str
    top_k: int
    top_n: int
    filters: MatchFilters
    corpus_profile: str
    took_ms: float
    created_at: datetime
    results: list[JobMatch]


class HistoryPatchRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)


class ImportEntry(BaseModel):
    """One `localStorage` history entry being migrated server-side. Field names
    are snake_case to match this API's own convention -- the frontend (enhancements/
    23) is responsible for mapping `HistoryEntry`'s camelCase shape onto this one,
    same as it already does for `MatchRequestBody`'s `topK`/`top_k`.
    """

    created_at: int = Field(description="epoch milliseconds, matching HistoryEntry.createdAt")
    label: str = Field(max_length=80)
    resume_text: str
    top_k: int
    top_n: int
    filters: MatchFilters
    results: list[JobMatch]


class ImportRequest(BaseModel):
    entries: list[ImportEntry]


class ImportResult(BaseModel):
    imported: int
    skipped_duplicate: int
    skipped_quota: int


# --- Saved lists ---------------------------------------------------------------


class ListCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ListRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ListItemRequest(BaseModel):
    job_id: int
    job_title: str = Field(max_length=255)
    job_family: str = Field(max_length=64)
    note: str | None = Field(default=None, max_length=1000)


class SavedListItemOut(BaseModel):
    job_id: int
    job_title: str
    job_family: str
    note: str | None
    created_at: datetime


class SavedListSummary(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    item_count: int


class SavedListDetail(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    items: list[SavedListItemOut]


# --- Feedback ------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    job_id: int
    signal: Literal["up", "down", "click"]
    rank: int = Field(ge=1)  # the position this result held when the signal fired -- never optional
    resume_hash: str  # from MatchResponse
    # A real uuid.UUID, not str: a malformed value is a clean 422 at the schema
    # layer, rather than something the route has to decide how to degrade.
    run_id: UUID | None = None


class FeedbackResponse(BaseModel):
    id: str | None
    action: Literal["created", "removed"]


class FeedbackStateOut(BaseModel):
    """One row of `GET /me/feedback`: the caller's own `up`/`down` signals for a
    given run, so a reloaded page can show a signal as still toggled on without
    the client having to remember it. `click` is never returned here -- it isn't a
    toggle state anything renders, only a one-way relevance signal."""

    job_id: int
    signal: Literal["up", "down"]
