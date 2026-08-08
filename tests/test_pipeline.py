import pytest

from src.talentrank import pipeline
from src.talentrank.models import ModelBundle


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
