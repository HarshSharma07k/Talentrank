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
