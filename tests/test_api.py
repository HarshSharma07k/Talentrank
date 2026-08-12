"""Tests for the FastAPI contract. See .claude/enhancements/02 and /03.

`client` (from conftest.py) is `TestClient(app)` with `get_model_bundle` overridden to
`fake_bundle` -- a real `ModelBundle` built from synthetic fixtures (a real 20-vector
FAISS index, a real 20-row DataFrame, deterministic stub encoders). `lifespan` never
runs and no real model or FAISS index loads.
"""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient
import httpx
import pytest

from src.talentrank import rerank as rerank_module
from src.talentrank.cache import get_cache_backend
from src.talentrank.config import get_settings
from src.talentrank.models import ModelBundle, get_model_bundle

MIN_RESUME_CHARS = 40


async def _register(client: httpx.AsyncClient, email: str, password: str = "correct-horse-battery") -> str:
    response = await client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201
    return response.json()["token"]


def test_health_shape(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    for field in (
        "status",
        "version",
        "device",
        "warm",
        "corpus_profile",
        "corpus_size",
        "index_size",
        "bi_encoder",
        "cross_encoder",
        "cache_backend",
        "uptime_seconds",
    ):
        assert field in body
    assert body["corpus_size"] == 20
    assert body["index_size"] == 20
    assert body["warm"] is True


def test_health_reports_live_cache_backend_not_configured_one(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Redis backend that's configured but unreachable degrades to in-memory
    inside get_cache_backend() (see enhancements/07) -- /health must report that
    real fallback, not just echo settings.cache_backend, or it would claim
    "redis" while every request is actually served from memory. See
    enhancements/14."""

    monkeypatch.setenv("TALENTRANK_CACHE_BACKEND", "redis")
    monkeypatch.setenv("TALENTRANK_REDIS_URL", "redis://127.0.0.1:6399/0")  # nothing listens here
    get_settings.cache_clear()
    get_cache_backend.cache_clear()

    assert get_settings().cache_backend == "redis"  # the configured intent

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["cache_backend"] == "memory"  # the actual live backend


def test_match_response_validates(client: TestClient) -> None:
    response = client.post("/match", json={"resume_text": "x" * 50, "top_k": 10, "top_n": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "rerank"
    assert len(body["results"]) == 5
    assert [r["rank"] for r in body["results"]] == list(range(1, 6))
    scores = [r["cross_encoder_score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)


def test_resume_too_short_422(client: TestClient) -> None:
    response = client.post("/match", json={"resume_text": "x" * (MIN_RESUME_CHARS - 1)})

    assert response.status_code == 422
    assert "detail" in response.json()


def test_resume_too_long_422(client: TestClient) -> None:
    response = client.post("/match", json={"resume_text": "x" * 20_001})

    assert response.status_code == 422


def test_top_k_out_of_range_422(client: TestClient) -> None:
    response = client.post("/match", json={"resume_text": "x" * 50, "top_k": 999_999})

    assert response.status_code == 422


def test_retrieve_stage_field(client: TestClient) -> None:
    response = client.post("/retrieve", json={"resume_text": "x" * 50, "top_k": 10, "top_n": 3})

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "retrieve"
    assert body["results"]
    assert all(r["cross_encoder_score"] == 0.0 for r in body["results"])


def test_job_families_endpoint(client: TestClient) -> None:
    response = client.get("/job-families")

    assert response.status_code == 200
    body = response.json()
    assert body  # fake_bundle's 20 synthetic titles produce a non-empty facet list
    assert sum(row["count"] for row in body) == 20
    assert body[-1]["family"] == "OTHER"  # OTHER is always forced last, regardless of its count
    assert body[-1]["label"] == "Other"
    counts = [row["count"] for row in body[:-1]]
    assert counts == sorted(counts, reverse=True)
    public_relations = next(row for row in body if row["family"] == "PUBLIC-RELATIONS")
    assert public_relations["label"] == "Public Relations"


def test_match_family_filter(client: TestClient) -> None:
    response = client.post(
        "/match",
        json={"resume_text": "x" * 50, "top_k": 20, "top_n": 20, "filters": {"job_families": ["HEALTHCARE"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"]
    assert {r["job_family"] for r in body["results"]} == {"HEALTHCARE"}
    assert body["filtered_candidates"] <= body["total_candidates"]


def test_match_family_filter_empty_result_stays_honest(client: TestClient) -> None:
    """A family with zero matches in the corpus returns an empty (not erroring)
    result list, with counts that say so honestly rather than silently."""

    response = client.post(
        "/match",
        json={"resume_text": "x" * 50, "top_k": 20, "top_n": 20, "filters": {"job_families": ["AGRICULTURE"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert body["filtered_candidates"] == 0


def test_missing_artifacts_returns_503(client: TestClient) -> None:
    from src.talentrank.api import app

    def raise_not_found() -> ModelBundle:
        raise FileNotFoundError("jobs.faiss not found")

    app.dependency_overrides[get_model_bundle] = raise_not_found

    response = client.post("/match", json={"resume_text": "x" * 50})

    assert response.status_code == 503
    assert "detail" in response.json()


def test_payload_excludes_raw_text(client: TestClient) -> None:
    response = client.post("/match", json={"resume_text": "x" * 50})

    body = response.json()
    assert body["results"]
    for result in body["results"]:
        assert "text" not in result
        assert "job_text" not in result


def test_second_identical_match_is_cached(client: TestClient) -> None:
    """Regression: a cache hit used to replay the stored (uncached) `took_ms`
    verbatim, so a near-instant lookup misreported itself as an 800ms rerank pass."""

    payload = {"resume_text": "y" * 60, "top_k": 10, "top_n": 3}

    first = client.post("/match", json=payload)
    second = client.post("/match", json=payload)

    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["took_ms"] != first.json()["took_ms"]


def test_rate_limit_429(client: TestClient) -> None:
    settings = get_settings()
    settings.rate_limit_requests = 2
    settings.rate_limit_window_seconds = 60

    responses = [client.get("/health") for _ in range(3)]

    assert [r.status_code for r in responses] == [200, 200, 429]
    assert responses[-1].headers["Retry-After"] == "60"


def test_semaphore_timeout_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings().inference_queue_timeout_seconds = 0.05
    held_semaphore = threading.BoundedSemaphore(1)
    held_semaphore.acquire()  # simulate an in-flight request already holding the only slot
    monkeypatch.setattr(rerank_module, "_INFERENCE_SEMAPHORE", held_semaphore)

    response = client.post("/match", json={"resume_text": "x" * 50})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"


@pytest.mark.anyio
async def test_run_id_not_shared_across_users_on_cache_hit(async_client: httpx.AsyncClient) -> None:
    """The one test standing between this design and a cross-account data leak.
    See enhancements/21's own "finding this document exists because of": the match
    cache has no principal component, so `run_id` must be attached *after* the
    cache lookup returns, never serialized into the cached payload -- otherwise
    user B's cache hit on the identical request would return user A's `run_id`.
    """

    token_a = await _register(async_client, "cacheuser-a@example.com")
    token_b = await _register(async_client, "cacheuser-b@example.com")

    payload = {"resume_text": "x" * 60}
    response_a = await async_client.post("/match", json=payload, headers={"Authorization": f"Bearer {token_a}"})
    response_b = await async_client.post("/match", json=payload, headers={"Authorization": f"Bearer {token_b}"})

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    body_a = response_a.json()
    body_b = response_b.json()

    assert body_a["cached"] is False  # first-ever request for this exact resume text
    assert body_b["cached"] is True  # identical request -- the shared cache serves it

    assert body_a["run_id"] is not None
    assert body_b["run_id"] is not None
    assert body_a["run_id"] != body_b["run_id"]

    # Each run_id must point at a row the respective user actually owns.
    own_a = await async_client.get(f"/me/history/{body_a['run_id']}", headers={"Authorization": f"Bearer {token_a}"})
    own_b = await async_client.get(f"/me/history/{body_b['run_id']}", headers={"Authorization": f"Bearer {token_b}"})
    assert own_a.status_code == 200
    assert own_b.status_code == 200

    # User A must not be able to read user B's run under the run_id the cache hit gave B.
    cross = await async_client.get(f"/me/history/{body_b['run_id']}", headers={"Authorization": f"Bearer {token_a}"})
    assert cross.status_code == 404


@pytest.mark.anyio
async def test_match_anonymous_has_null_run_id(async_client: httpx.AsyncClient) -> None:
    response = await async_client.post("/match", json={"resume_text": "x" * MIN_RESUME_CHARS})

    assert response.status_code == 200
    assert response.json()["run_id"] is None


@pytest.mark.anyio
async def test_match_persists_history_for_authenticated_user(async_client: httpx.AsyncClient) -> None:
    token = await _register(async_client, "history-user@example.com")

    response = await async_client.post(
        "/match", json={"resume_text": "x" * 55}, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    run_id = response.json()["run_id"]
    assert run_id is not None

    detail = await async_client.get(f"/me/history/{run_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200


@pytest.mark.anyio
async def test_match_succeeds_when_persistence_fails(
    async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves the best-effort guard: a persistence failure must never fail a match."""

    from src.talentrank.userdata import history as history_module

    async def _raise(*args: object, **kwargs: object) -> str | None:
        raise RuntimeError("simulated persistence outage")

    monkeypatch.setattr(history_module, "persist_run", _raise)

    token = await _register(async_client, "persist-fail@example.com")
    response = await async_client.post(
        "/match", json={"resume_text": "x" * 55}, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["run_id"] is None


@pytest.mark.anyio
async def test_match_response_resume_hash_matches_pipeline_digest(async_client: httpx.AsyncClient) -> None:
    from src.talentrank import pipeline

    resume_text = "x" * 55
    response = await async_client.post("/match", json={"resume_text": resume_text})

    assert response.status_code == 200
    assert response.json()["resume_hash"] == pipeline.resume_digest(resume_text)


def test_anonymous_match_works_with_database_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression guard for enhancements/21's own explicit risk note: an
    anonymous /match call must never touch the database at all, so even a
    completely broken DB dependency cannot break the public matching path.

    Deliberately uses the plain sync `client` fixture, not `async_client` --
    `async_client` overrides `get_db`, which would mask exactly the regression
    this test exists to catch (a `Depends(get_db)` re-introduced somewhere in
    `/match`'s dependency chain). `client` never overrides it, so a real,
    unconditional DB dependency would actually hit the monkeypatched, raising
    `get_sessionmaker`/`get_engine` below.
    """

    from src.talentrank.db import session as db_session_module

    def _boom() -> object:
        raise RuntimeError("the database is unreachable")

    monkeypatch.setattr(db_session_module, "get_sessionmaker", _boom)
    monkeypatch.setattr(db_session_module, "get_engine", _boom)

    response = client.post("/match", json={"resume_text": "x" * MIN_RESUME_CHARS})

    assert response.status_code == 200
    assert response.json()["run_id"] is None


@pytest.mark.anyio
async def test_match_handler_does_not_block_event_loop(
    async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards the async-conversion trap: the CPU-bound retrieve+rerank work must run
    via `anyio.to_thread.run_sync`, never directly on the event loop -- dropping
    that would stall every concurrent request behind a multi-hundred-millisecond
    synchronous call, undoing enhancements/08's whole latency effort. A single
    request's assertion is enough to prove the threadpool hop happened; it
    wouldn't show up at all in a test that only checked the response was correct.
    """

    import anyio.to_thread

    from src.talentrank import api as api_module

    calls: list[object] = []
    original_run_sync = anyio.to_thread.run_sync

    async def spy_run_sync(func: object, *args: object, **kwargs: object) -> object:
        calls.append(func)
        return await original_run_sync(func, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(api_module.anyio.to_thread, "run_sync", spy_run_sync)

    response = await async_client.post("/match", json={"resume_text": "x" * MIN_RESUME_CHARS})

    assert response.status_code == 200
    # `anyio.to_thread.run_sync` is patched globally, so `httpx.AsyncClient`'s own
    # internals (unrelated to this request) also show up in `calls` -- filter to
    # the pipeline call specifically, identifiable by the enclosing function's name
    # on the lambda `match_resume` wraps it in.
    match_calls = [c for c in calls if getattr(c, "__qualname__", "").startswith("match_resume")]
    assert len(match_calls) == 1
