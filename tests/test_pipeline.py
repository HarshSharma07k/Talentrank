import pytest

from src.talentrank import pipeline


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
