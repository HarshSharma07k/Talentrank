"""Shared fixtures. Deliberately synthetic: no test in this suite may touch
`data/` or download model weights, so CI can run against a clean checkout.
"""

from __future__ import annotations

from collections.abc import Iterator
import hashlib

import numpy as np
import pandas as pd
import pytest

from src.talentrank.config import get_settings
from src.talentrank.index import FaissIndexManager


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """`get_settings` is `@lru_cache`'d; a test that sets env vars must not leak
    its Settings into the next test. Extend this fixture as more `@lru_cache`d
    getters (model bundle, cache backend) land in later phases.
    """

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
    `TextEmbeddingEncoder._model` directly in tests without a network call.
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
