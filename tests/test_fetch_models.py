"""Tests for `scripts/fetch_models.py`. See enhancements/14.

Never downloads real weights -- `SentenceTransformer`/`CrossEncoder` are replaced
with recording stubs. What's under test is that the script asks for whatever
`get_settings()` resolves to, not a hardcoded string that could silently drift
from what `models.py` requests at runtime (the exact failure mode enhancements/14's
risk note calls out for `cross_encoder_model_name`).
"""

from __future__ import annotations

import pytest

from scripts import fetch_models
from src.talentrank.config import get_settings


def test_fetch_models_uses_settings_not_hardcoded_names(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, tuple, dict]] = []

    def fake_sentence_transformer(*args: object, **kwargs: object) -> None:
        calls.append(("bi_encoder", args, kwargs))

    def fake_cross_encoder(*args: object, **kwargs: object) -> None:
        calls.append(("cross_encoder", args, kwargs))

    monkeypatch.setattr(fetch_models, "SentenceTransformer", fake_sentence_transformer)
    monkeypatch.setattr(fetch_models, "CrossEncoder", fake_cross_encoder)

    fetch_models.fetch_models()

    settings = get_settings()
    kinds = [kind for kind, _, _ in calls]
    assert kinds == ["bi_encoder", "cross_encoder"]

    bi_args = calls[0][1]
    assert bi_args[0] == settings.bi_encoder_model_name

    cross_args, cross_kwargs = calls[1][1], calls[1][2]
    assert cross_args[0] == settings.cross_encoder_model_name
    assert cross_kwargs["max_length"] == settings.cross_encoder_max_length


def test_cross_encoder_id_carries_the_org_prefix() -> None:
    """Regression guard for the exact bug enhancements/14 flags: a bare
    "ms-marco-MiniLM-L-6-v2" resolves via an org fallback at request time but
    isn't guaranteed to be what got baked into the image's offline HF cache."""

    assert get_settings().cross_encoder_model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"
