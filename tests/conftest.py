"""Shared fixtures. Deliberately synthetic: no test in this suite may touch
`data/` or download model weights, so CI can run against a clean checkout.
"""

from __future__ import annotations

from collections.abc import Iterator
import hashlib
import time

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.talentrank.cache import get_cache_backend
from src.talentrank.config import get_settings
from src.talentrank.index import FaissIndexManager
from src.talentrank.models import ModelBundle, get_model_bundle

_LRU_CACHED_GETTERS = (
    get_settings,
    get_model_bundle,
    get_cache_backend,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """These are all `@lru_cache`'d. Without clearing them, a test that monkeypatches
    a loader (or sets an env var `get_settings` reads) can leak its stub/value into
    the next test -- or worse, a real value cached from actual `data/` on a dev
    machine can mask what should be a `FileNotFoundError` in the `data/`-absent CI
    run. Extend this tuple as more `@lru_cache`'d getters (cache backend, `03`) land
    in later phases.
    """

    for getter in _LRU_CACHED_GETTERS:
        getter.cache_clear()
    yield
    for getter in _LRU_CACHED_GETTERS:
        getter.cache_clear()


_JOB_TITLES = [
    "Senior Software Engineer",
    "Registered Nurse",
    "Sales Associate",
    "Staff Accountant",
    "Construction Project Manager",
    "Management Consultant",
    "HR Generalist",
    "High School Teacher",
    "Bank Teller",
    "Graphic Designer",
    "Automobile Technician",
    "Executive Chef",
    "Public Relations Specialist",
    "Fitness Instructor",
    "Digital Media Producer",
    "Apparel Buyer",
    "Fine Artist",
    "Flight Attendant",
    "Agricultural Technician",
    "Business Development Manager",
]


class StubBiEncoder:
    """Deterministic stand-in for `SentenceTransformer.encode`.

    Same call signature as the real model so it can replace
    `TextEmbeddingEncoder._model` (or `ModelBundle.bi_encoder`) directly in tests
    without a network call.
    """

    def encode(
        self,
        texts: list[str],
        batch_size: int = 64,
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        vectors = np.stack([self._vector_for(text) for text in texts])
        return vectors

    @staticmethod
    def _vector_for(text: str) -> np.ndarray:
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
        vector = np.random.default_rng(seed).normal(size=384).astype(np.float32)
        return vector / np.linalg.norm(vector)


class StubCrossEncoder:
    """Deterministic stand-in for `CrossEncoder.predict`."""

    def predict(self, pairs: list[list[str]]) -> np.ndarray:
        scores = [
            (int(hashlib.sha256((query + text).encode("utf-8")).hexdigest()[:8], 16) % 1000) / 1000.0
            for query, text in pairs
        ]
        return np.asarray(scores, dtype=np.float32)


@pytest.fixture
def stub_bi_encoder() -> StubBiEncoder:
    return StubBiEncoder()


@pytest.fixture
def tiny_jobs_frame() -> pd.DataFrame:
    """20 rows, same columns as the real cleaned parquet, spanning several job titles."""

    descriptions = [f"{title} responsible for day-to-day operations and delivering results." for title in _JOB_TITLES]
    return pd.DataFrame(
        {
            "job_id": list(range(1, len(_JOB_TITLES) + 1)),
            "job_title": _JOB_TITLES,
            "description": descriptions,
            "skills": ["" for _ in _JOB_TITLES],
            "text": descriptions,
            "job_category": [title.upper() for title in _JOB_TITLES],
        }
    )


@pytest.fixture
def tiny_index() -> FaissIndexManager:
    """A real FAISS index over 20 random normalized 384-d vectors. Milliseconds to build."""

    rng = np.random.default_rng(seed=42)
    vectors = rng.normal(size=(20, 384)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)

    manager = FaissIndexManager(dimension=384)
    manager.add(vectors, job_ids=list(range(1, 21)))
    return manager


@pytest.fixture
def fake_bundle(
    tiny_jobs_frame: pd.DataFrame, tiny_index: FaissIndexManager, stub_bi_encoder: StubBiEncoder
) -> ModelBundle:
    """A `ModelBundle` built entirely from synthetic fixtures. `models.get_model_bundle`
    indexes the jobs frame by string `job_id` before handing it out; mirror that here
    so `pipeline._resolve_job_row`'s `.loc[str_id]` lookup works the same way it does
    against a real bundle.
    """

    indexed_jobs = tiny_jobs_frame.copy()
    indexed_jobs["job_id"] = indexed_jobs["job_id"].astype(str)
    indexed_jobs = indexed_jobs.set_index("job_id")

    return ModelBundle(
        device="cpu",
        bi_encoder=stub_bi_encoder,
        cross_encoder=StubCrossEncoder(),
        index=tiny_index,
        jobs=indexed_jobs,
        idf={},
        families=[],
        loaded_at=time.monotonic(),
        warm=True,
    )


@pytest.fixture
def client(fake_bundle: ModelBundle) -> Iterator[TestClient]:
    """`TestClient(app)` used as a plain instance, so `lifespan` never runs and no
    real model or FAISS index loads -- see enhancements/17's note on this. The route
    dependency is swapped for `fake_bundle` instead.
    """

    from src.talentrank.api import app

    app.dependency_overrides[get_model_bundle] = lambda: fake_bundle
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
