"""Tests for the cross-encoder reranking levers in .claude/enhancements/08."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from src.talentrank import rerank as rerank_module
from src.talentrank.config import get_settings
from src.talentrank.rerank import _candidate_text, rerank


def test_text_truncated_to_max_chars() -> None:
    get_settings().rerank_text_max_chars = 10
    candidate = {"job_text": "a" * 50}

    assert _candidate_text(candidate) == "a" * 10


def test_retrieval_rank_survives_reordering() -> None:
    """`rerank()` copies each candidate dict (`dict(candidate)`) and only adds
    `cross_encoder_score` before re-sorting -- it must never touch a field the
    candidate already carried. `retrieval_rank` (set by `retrieve_only`, before
    rerank ever runs) is the one that matters most: `JobCard.tsx`'s rank-delta
    badge is built entirely on `retrieval_rank` still reflecting each job's
    *original* FAISS position after the cross-encoder reorders everything. See
    enhancements/17."""

    class _ReversingCrossEncoder:
        """Scores candidates in exactly the reverse of their input order, so
        rerank's sort is guaranteed to actually move something."""

        def predict(self, pairs: list[list[str]]) -> list[float]:
            return list(range(len(pairs)))  # last input pair scores highest

    candidates = [
        {"job_id": 1, "job_text": "a", "retrieval_rank": 1},
        {"job_id": 2, "job_text": "b", "retrieval_rank": 2},
        {"job_id": 3, "job_text": "c", "retrieval_rank": 3},
    ]

    ranked = rerank("query", candidates, top_n=3, model=_ReversingCrossEncoder())

    assert [c["job_id"] for c in ranked] == [3, 2, 1]  # order did change
    assert [c["retrieval_rank"] for c in ranked] == [3, 2, 1]  # original rank preserved per job


def test_max_length_passed_to_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """`rerank`'s fallback (uncached-caller) `CrossEncoder` construction must thread
    `settings.cross_encoder_max_length` through as the constructor argument -- see
    enhancements/08 lever B. The primary path (`models.get_model_bundle`) is covered
    separately in test_models.py."""

    get_settings().cross_encoder_max_length = 123
    captured: dict[str, Any] = {}

    class _FakeCrossEncoder:
        def __init__(self, model_name: str, max_length: int | None = None) -> None:
            captured["model_name"] = model_name
            captured["max_length"] = max_length

        def predict(self, pairs: list[list[str]]) -> np.ndarray:
            return np.zeros(len(pairs), dtype=np.float32)

    monkeypatch.setattr(rerank_module, "CrossEncoder", _FakeCrossEncoder)

    rerank("query", [{"job_id": 1, "job_text": "a job"}], top_n=1, model=None)

    assert captured["max_length"] == 123
