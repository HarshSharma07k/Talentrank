import pytest

from src.talentrank import pipeline
from src.talentrank.models import ModelBundle
from src.talentrank.schemas import MatchFilters


def test_retrieve_empty_resume() -> None:
    assert pipeline.retrieve_only("", top_k=5) == []


def test_match_invalid_k_n(monkeypatch: pytest.MonkeyPatch) -> None:
    assert pipeline.match("", top_k=0, top_n=5) == []

    monkeypatch.setattr(
        pipeline,
        "retrieve_only",
        lambda resume_text, top_k, bundle=None: [{"job_id": 1, "job_text": "example"}],
    )

    assert pipeline.match("resume text", top_k=5, top_n=0) == []


def test_overfetch_only_when_filtering(monkeypatch: pytest.MonkeyPatch, fake_bundle: ModelBundle) -> None:
    """A family filter over-fetches from FAISS by `filter_overfetch_factor`; with no
    family filter, `retrieve_only` sees the requested `top_k` unchanged. See
    enhancements/05, `_effective_retrieval_top_k`."""

    from src.talentrank.config import get_settings

    original_retrieve_only = pipeline.retrieve_only
    captured_top_k: list[int] = []

    def spy_retrieve_only(resume_text: str, top_k: int, bundle: ModelBundle | None = None) -> list:
        captured_top_k.append(top_k)
        return original_retrieve_only(resume_text, top_k=top_k, bundle=bundle)

    monkeypatch.setattr(pipeline, "retrieve_only", spy_retrieve_only)

    pipeline.match_response("x" * 50, top_k=5, top_n=3, bundle=fake_bundle, explain=False)
    assert captured_top_k[-1] == 5

    pipeline.match_response(
        "x" * 50,
        top_k=5,
        top_n=3,
        bundle=fake_bundle,
        explain=False,
        filters=MatchFilters(job_families=["HEALTHCARE"]),
    )
    assert captured_top_k[-1] == 5 * get_settings().filter_overfetch_factor


def test_counts_reported(fake_bundle: ModelBundle) -> None:
    """`filtered_candidates` never exceeds `total_candidates`, and with no filters
    set the two are equal (nothing was dropped)."""

    unfiltered = pipeline.match_response("x" * 50, top_k=20, top_n=20, bundle=fake_bundle, explain=False)
    assert unfiltered.filtered_candidates == unfiltered.total_candidates

    filtered = pipeline.match_response(
        "x" * 50,
        top_k=20,
        top_n=20,
        bundle=fake_bundle,
        explain=False,
        filters=MatchFilters(min_score=0.9),
    )
    assert filtered.filtered_candidates <= filtered.total_candidates


def test_cached_match_key_is_whitespace_insensitive(fake_bundle: ModelBundle) -> None:
    """The cache key hashes whitespace-normalized text -- the same normalization
    `retrieve_only` applies before embedding -- so a request that differs from a
    previous one only in incidental whitespace still hits. This is what makes
    `models.warmup`'s cache-warm of `SAMPLE_RESUME` (enhancements/08) reliable rather
    than contingent on two source files staying character-for-character identical."""

    resume = "x" * 20 + "  " + "y" * 20  # internal whitespace to normalize
    padded_resume = f"  {resume}  \n"

    first = pipeline.cached_match(resume, top_k=5, top_n=3, bundle=fake_bundle)
    second = pipeline.cached_match(padded_resume, top_k=5, top_n=3, bundle=fake_bundle)

    assert first.cached is False
    assert second.cached is True
