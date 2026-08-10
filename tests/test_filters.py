"""Tests for `data.derive_job_family` and `filters.apply_filters`. See enhancements/05."""

from __future__ import annotations

from src.talentrank.data import derive_job_family
from src.talentrank.filters import apply_filters
from src.talentrank.schemas import MatchFilters


def test_family_derivation_known_titles() -> None:
    assert derive_job_family("Registered Nurse") == "HEALTHCARE"
    assert derive_job_family("Xylophone Tuning Coordinator") == "OTHER"


def test_family_derivation_is_deterministic() -> None:
    title = "Senior Software Engineer"
    assert derive_job_family(title) == derive_job_family(title)


def _candidate(job_id: int, job_family: str, cross_encoder_score: float | None = None) -> dict:
    candidate = {"job_id": job_id, "job_family": job_family}
    if cross_encoder_score is not None:
        candidate["cross_encoder_score"] = cross_encoder_score
    return candidate


def test_min_score_filter() -> None:
    """Filters on `cross_encoder_probability` (sigmoid of the logit), not the raw
    logit -- a raw logit has no fixed [0, 1] range, so a threshold only means
    anything against the sigmoid."""

    candidates = [
        _candidate(1, "SALES", cross_encoder_score=5.0),  # sigmoid ~0.993
        _candidate(2, "SALES", cross_encoder_score=-5.0),  # sigmoid ~0.007
    ]
    filters = MatchFilters(min_score=0.5)

    result = apply_filters(candidates, filters)

    assert [c["job_id"] for c in result] == [1]


def test_min_score_filter_is_a_noop_before_rerank() -> None:
    """Before rerank, no candidate carries `cross_encoder_score` yet -- `apply_filters`
    must not treat a missing score as 0.0 and wrongly drop everything."""

    candidates = [_candidate(1, "SALES"), _candidate(2, "SALES")]
    filters = MatchFilters(min_score=0.9)

    result = apply_filters(candidates, filters)

    assert [c["job_id"] for c in result] == [1, 2]


def test_family_filter_multi_select() -> None:
    candidates = [
        _candidate(1, "HEALTHCARE"),
        _candidate(2, "SALES"),
        _candidate(3, "ENGINEERING"),
    ]
    filters = MatchFilters(job_families=["HEALTHCARE", "SALES"])

    result = apply_filters(candidates, filters)

    assert {c["job_id"] for c in result} == {1, 2}


def test_no_filters_is_a_noop() -> None:
    candidates = [_candidate(1, "HEALTHCARE"), _candidate(2, "SALES")]

    assert apply_filters(candidates, MatchFilters()) == candidates
