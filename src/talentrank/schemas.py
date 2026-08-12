"""Pydantic request/response models for the TalentRank API.

`explanation`/`scores.skill_overlap` are real as of `04`; `job_family` and filtering
(`MatchFilters`, `filtered_candidates`) are real as of `05`. See enhancements/02.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.talentrank.config import get_settings

_settings = get_settings()


class MatchFilters(BaseModel):
    """Optional result filters, applied server-side by `filters.apply_filters` --
    see enhancements/05. `job_families` filters on `job_family` before rerank (with a
    FAISS over-fetch so a narrow family still gets a real shortlist); `min_score`
    filters on `cross_encoder_probability` after rerank."""

    job_families: list[str] | None = None
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)


class MatchRequest(BaseModel):
    """Request body for `/match` and `/retrieve`."""

    resume_text: str = Field(min_length=_settings.min_resume_chars, max_length=_settings.max_resume_chars)
    top_k: int = Field(default=_settings.default_top_k, ge=1, le=_settings.max_top_k)
    top_n: int = Field(default=_settings.default_top_n, ge=1, le=_settings.max_top_n)
    filters: MatchFilters = Field(default_factory=MatchFilters)
    explain: bool = True  # gates the enhancements/04 lexical evidence layer


class ScoreBreakdown(BaseModel):
    """All score components for one job match, for a transparent UI."""

    bi_encoder: float  # cosine in [-1, 1]: normalized embeddings + inner product
    cross_encoder: float  # raw logit, kept for transparency
    cross_encoder_probability: float  # sigmoid(logit) in [0, 1] -- the display number
    skill_overlap: float  # [0, 1]; from Explanation.overlap_score when explain=True, else 0.0


class MatchedTerm(BaseModel):
    term: str
    weight: float


class Explanation(BaseModel):
    """Lexical evidence layer built by `explain.explain_candidate` (enhancements/04).
    `None` on a `JobMatch` only when the request set `explain=False`."""

    matched_skills: list[str]
    missing_skills: list[str]
    matched_terms: list[MatchedTerm]
    overlap_score: float


class JobMatch(BaseModel):
    """One ranked job result."""

    job_id: int
    job_title: str
    description: str  # server-truncated to settings.description_max_chars
    skills: str
    job_category: str
    job_family: str  # derived by data.derive_job_family; "OTHER" for the uncovered bucket, shown honestly
    bi_encoder_score: float
    cross_encoder_score: float
    scores: ScoreBreakdown
    explanation: Explanation | None = None
    retrieval_rank: int  # 1-based FAISS position -- enables the rank-delta badge
    rank: int  # 1-based final position in this response


class MatchResponse(BaseModel):
    results: list[JobMatch]
    stage: Literal["retrieve", "rerank"]
    top_k: int
    top_n: int
    total_candidates: int  # retrieved, before filtering
    filtered_candidates: int  # survived family + min_score filters, before the top_n slice
    took_ms: float
    cached: bool
    corpus_size: int
    resume_hash: str  # pipeline.resume_digest(resume_text) -- a pure function of the request, safe to cache
    # match_runs.id for the row persisted for *this* caller, enhancements/21. None
    # for anonymous requests and when persistence was skipped or failed. Must be
    # attached AFTER the cache lookup, never computed inside match_response/
    # cached_match -- see pipeline.py's own note on why.
    run_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    device: str
    warm: bool
    corpus_profile: str
    corpus_size: int
    index_size: int
    bi_encoder: str
    cross_encoder: str
    cache_backend: str
    uptime_seconds: float


class JobFamilyCount(BaseModel):
    """One row of `GET /job-families`, computed once at startup by
    `models._compute_job_families` from the loaded frame's `job_family` column --
    see enhancements/05. Sorted by count descending with `OTHER` forced last."""

    family: str  # "INFORMATION-TECHNOLOGY"
    label: str  # "Information Technology" (reuse formatCategory's logic server-side)
    count: int


class ExtractTextResponse(BaseModel):
    """Response for `POST /extract-text`. See enhancements/06 -- deliberately a
    separate endpoint from `/match` so the user sees and edits this text before it
    is ever matched."""

    text: str
    char_count: int
    page_count: int | None  # None for DOCX
    filename: str
    truncated: bool
