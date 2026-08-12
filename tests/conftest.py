"""Shared fixtures. Deliberately synthetic: no test in this suite may touch
`data/` or download model weights, so CI can run against a clean checkout.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
import hashlib
import time

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.talentrank.auth.passwords import get_password_hasher
from src.talentrank.cache import get_cache_backend
from src.talentrank.config import get_settings
from src.talentrank.data import derive_job_family
from src.talentrank.db import models as db_models  # noqa: F401 -- registers all six tables on Base.metadata
from src.talentrank.db.base import Base
from src.talentrank.db.session import get_db, get_engine, get_sessionmaker
from src.talentrank.index import FaissIndexManager
from src.talentrank.models import ModelBundle, _compute_job_families, get_model_bundle

_LRU_CACHED_GETTERS = (
    get_settings,
    get_model_bundle,
    get_cache_backend,
    get_engine,
    get_sessionmaker,
    get_password_hasher,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """In-memory SQLite with `StaticPool`, schema via `Base.metadata.create_all`.

    `StaticPool` is required: with the default pool, every connection to
    `sqlite+aiosqlite:///:memory:` gets its *own* empty database, so a fixture that
    creates tables on one connection and a test that queries on another sees
    nothing. In-memory also keeps the binding invariant intact -- no test writes a
    file, so the suite still passes with `data/` absent.
    """

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection: object, connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session


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
            "job_family": [derive_job_family(title) for title in _JOB_TITLES],
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
        families=_compute_job_families(indexed_jobs),
        loaded_at=time.monotonic(),
        warm=True,
    )


@pytest.fixture
def client(fake_bundle: ModelBundle) -> Iterator[TestClient]:
    """`TestClient(app)` used as a plain instance, so `lifespan` never runs and no
    real model or FAISS index loads -- see enhancements/17's note on this. The route
    dependency is swapped for `fake_bundle` instead.

    Deliberately does **not** override `get_db` (enhancements/19's own doc sketch
    suggested extending this fixture with a `db_session` parameter): `client` is a
    plain sync fixture used by dozens of existing sync tests, and `db_session` is an
    async fixture -- pytest cannot resolve an async fixture as a sync fixture's
    dependency without every *consuming* test also being anyio-marked, which broke
    22 existing tests when tried. Worse, `TestClient` runs requests through its own
    internal event-loop portal thread, separate from whatever loop a pytest async
    fixture runs on -- handing a pre-built `AsyncSession` to a `get_db` override
    would raise "attached to a different loop" the moment a real endpoint used it,
    per this doc's own risk note. No route depends on `get_db` yet (`19` is
    infrastructure only); wiring this correctly is `20`'s problem, once there is a
    real DB-backed endpoint to test against and choose the right pattern for.
    """

    from src.talentrank.api import app

    app.dependency_overrides[get_model_bundle] = lambda: fake_bundle
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def async_client(fake_bundle: ModelBundle, db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    """`httpx.AsyncClient` over `ASGITransport`, for tests that need a real DB-backed
    endpoint (enhancements/20's `/auth/*` routes). Unlike `TestClient`, this runs the
    ASGI app directly in the *same* event loop as the calling test coroutine -- no
    internal portal thread -- so `db_session`, built by the anyio-managed `db_engine`
    fixture, is safe to hand to a `get_db` override here. See `client`'s own
    docstring above for why this doesn't work through `TestClient`.
    """

    from src.talentrank.api import app

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_model_bundle] = lambda: fake_bundle
    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
