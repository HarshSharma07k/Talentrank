"""Pydantic request/response models for the TalentRank API.

Several fields here (`job_family`, `explanation`, `scores.skill_overlap`) describe
features that later enhancement docs implement -- they are always present with a
stable placeholder value (never omitted) so the response shape doesn't change again
once the frontend depends on it. See enhancements/02.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.talentrank.config import get_settings

_settings = get_settings()


class MatchFilters(BaseModel):
    """Optional result filters. Not yet applied by the pipeline -- see enhancements/05."""

    job_families: list[str] | None = None
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)


class MatchRequest(BaseModel):
    """Request body for `/match` and `/retrieve`."""

    resume_text: str = Field(min_length=_settings.min_resume_chars, max_length=_settings.max_resume_chars)
    top_k: int = Field(default=_settings.default_top_k, ge=1, le=_settings.max_top_k)
    top_n: int = Field(default=_settings.default_top_n, ge=1, le=_settings.max_top_n)
    filters: MatchFilters = Field(default_factory=MatchFilters)
    explain: bool = True  # not yet applied -- see enhancements/04


class ScoreBreakdown(BaseModel):
    """All score components for one job match, for a transparent UI."""

    bi_encoder: float  # cosine in [-1, 1]: normalized embeddings + inner product
    cross_encoder: float  # raw logit, kept for transparency
    cross_encoder_probability: float  # sigmoid(logit) in [0, 1] -- the display number
    skill_overlap: float  # [0, 1]; always 0.0 until enhancements/04 lands


class MatchedTerm(BaseModel):
    term: str
    weight: float


class Explanation(BaseModel):
    """Skill/term overlap explanation. Not yet produced -- see enhancements/04."""

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
    job_family: str  # always "OTHER" until enhancements/05 and /09 add real families
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
    filtered_candidates: int  # survived filters; equals total_candidates until enhancements/05
    took_ms: float
    cached: bool
    corpus_size: int


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
    """One row of `GET /job-families`. Defined here now (03) because `ModelBundle`
    needs the type for its `families` field; always `[]` until `05` computes it from
    the loaded frame and `09` gives `job_family` real values."""

    family: str  # "INFORMATION-TECHNOLOGY"
    label: str  # "Information Technology" (reuse formatCategory's logic server-side)
    count: int
