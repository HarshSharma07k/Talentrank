"""Tests for the model/corpus lifecycle seam. See .claude/enhancements/03 and /08."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import torch

from src.talentrank import models as models_module
from src.talentrank import pipeline as pipeline_module
from src.talentrank.index import FaissIndexManager
from src.talentrank.models import ModelBundle, _quantize_cross_encoder


def test_bundle_is_singleton(
    monkeypatch: pytest.MonkeyPatch,
    tiny_jobs_frame: pd.DataFrame,
    tiny_index: FaissIndexManager,
) -> None:
    """`get_model_bundle` is `@lru_cache`'d; two calls must return the same object.

    Every loading step is stubbed so this never touches `data/` -- `Path.exists` is
    patched process-wide for the duration of this test, which is safe because
    monkeypatch reverts it automatically at teardown.
    """

    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(models_module, "SentenceTransformer", lambda *args, **kwargs: object())
    monkeypatch.setattr(models_module, "CrossEncoder", lambda *args, **kwargs: object())
    monkeypatch.setattr(models_module.FaissIndexManager, "load_index", classmethod(lambda cls, path: tiny_index))
    monkeypatch.setattr(models_module, "_load_jobs_frame", lambda jobs_clean_path: tiny_jobs_frame)

    first = models_module.get_model_bundle()
    second = models_module.get_model_bundle()

    assert first is second


def test_warmup_sets_warm_flag(fake_bundle: ModelBundle) -> None:
    fake_bundle.warm = False

    models_module.warmup(fake_bundle)

    assert fake_bundle.warm is True


def test_warmup_populates_the_cache(fake_bundle: ModelBundle) -> None:
    """`warmup` goes through `cached_match`, not `match` -- see enhancements/08 lever
    E. The frontend's "Load sample resume" button sends `SAMPLE_RESUME` verbatim with
    default `top_k`/`top_n` and no filters, so a subsequent identical call must be a
    cache hit."""

    models_module.warmup(fake_bundle)

    settings = models_module.get_settings()
    response = pipeline_module.cached_match(
        models_module.SAMPLE_RESUME,
        top_k=settings.default_top_k,
        top_n=settings.default_top_n,
        bundle=fake_bundle,
    )

    assert response.cached is True


class _TinyLinearModel(torch.nn.Module):
    """Stand-in for `CrossEncoder.model`: a real container module with a nested
    `nn.Linear`, so `quantize_dynamic` has something to actually replace -- a bare
    top-level `nn.Linear` is not swapped by `quantize_dynamic` (verified manually;
    the traversal replaces matching *submodules*, not the root module itself)."""

    def __init__(self) -> None:
        super().__init__()
        self.linear = torch.nn.Linear(4, 4)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.linear(x)


class _FakeCrossEncoderOK:
    """`predict` succeeds regardless of whether `.model` has been quantized."""

    def __init__(self) -> None:
        self.model = _TinyLinearModel()
        self.predict_calls = 0

    def predict(self, pairs: list[list[str]]) -> list[float]:
        self.predict_calls += 1
        return [0.0 for _ in pairs]


def test_quantize_replaces_model_and_passes_self_test() -> None:
    cross_encoder = _FakeCrossEncoderOK()
    original_model = cross_encoder.model

    _quantize_cross_encoder(cross_encoder)

    assert cross_encoder.model is not original_model
    assert cross_encoder.predict_calls == 1  # the self-test ran


class _FakeCrossEncoderBroken:
    """`predict` raises once `.model.linear` has actually been swapped to the
    quantized dynamic type -- reproduces the real sentence-transformers 5.x /
    transformers 5.x incompatibility this project measured directly against its
    pinned versions (see `_quantize_cross_encoder`'s docstring)."""

    def __init__(self) -> None:
        self.model = _TinyLinearModel()

    def predict(self, pairs: list[list[str]]) -> list[float]:
        if not isinstance(self.model.linear, torch.nn.Linear):
            raise AttributeError("simulated post-quantization incompatibility")
        return [0.0 for _ in pairs]


def test_quantize_rolls_back_on_self_test_failure() -> None:
    cross_encoder = _FakeCrossEncoderBroken()
    original_model = cross_encoder.model

    _quantize_cross_encoder(cross_encoder)  # must not raise

    assert cross_encoder.model is original_model


def test_quantize_skips_when_model_attribute_missing() -> None:
    class _NoModelAttribute:
        pass

    _quantize_cross_encoder(_NoModelAttribute())  # must not raise
