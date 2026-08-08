"""Tests for the model/corpus lifecycle seam. See .claude/enhancements/03."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.talentrank import models as models_module
from src.talentrank.index import FaissIndexManager
from src.talentrank.models import ModelBundle


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
