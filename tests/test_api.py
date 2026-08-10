"""Tests for the FastAPI contract. See .claude/enhancements/02 and /03.

`client` (from conftest.py) is `TestClient(app)` with `get_model_bundle` overridden to
`fake_bundle` -- a real `ModelBundle` built from synthetic fixtures (a real 20-vector
FAISS index, a real 20-row DataFrame, deterministic stub encoders). `lifespan` never
runs and no real model or FAISS index loads.
"""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient
import pytest

from src.talentrank import rerank as rerank_module
from src.talentrank.config import get_settings
from src.talentrank.models import ModelBundle, get_model_bundle

MIN_RESUME_CHARS = 40


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
