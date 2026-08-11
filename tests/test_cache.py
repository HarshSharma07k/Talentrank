"""Tests for the process result cache. See .claude/enhancements/07."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from src.talentrank import cache as cache_module
from src.talentrank.cache import CacheStats, InMemoryTTLCache, RedisCache


def test_backend_name_attribute_identifies_which_is_live() -> None:
    """api.py's /health handler reads `.name` off whatever get_cache_backend()
    actually returns (enhancements/14) -- both backends must carry it. Checked
    as a class attribute for RedisCache so this doesn't need a real Redis server
    (instantiating it imports `redis` and opens a connection)."""

    assert InMemoryTTLCache().name == "memory"
    assert RedisCache.name == "redis"


def test_ttl_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 0.0}
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: clock["now"])

    cache = InMemoryTTLCache(max_entries=10)
    cache.set("k", b"v", ttl_seconds=5)
    assert cache.get("k") == b"v"

    clock["now"] = 5.1
    assert cache.get("k") is None


def test_lru_eviction() -> None:
    cache = InMemoryTTLCache(max_entries=2)

    cache.set("a", b"1", ttl_seconds=60)
    cache.set("b", b"2", ttl_seconds=60)
    cache.set("c", b"3", ttl_seconds=60)  # evicts "a", the oldest

    assert cache.get("a") is None
    assert cache.get("b") == b"2"
    assert cache.get("c") == b"3"


def test_thread_safety() -> None:
    cache = InMemoryTTLCache(max_entries=1000)

    def _write(i: int) -> None:
        cache.set(f"key-{i}", str(i).encode(), ttl_seconds=60)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(_write, range(500)))

    stats = cache.stats()
    assert stats.entries == 500
    for i in range(500):
        assert cache.get(f"key-{i}") == str(i).encode()


class _BrokenBackend:
    """A backend whose get/set always raise -- simulates a Redis outage."""

    def get(self, key: str) -> bytes | None:
        raise ConnectionError("simulated backend outage")

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        raise ConnectionError("simulated backend outage")

    def stats(self) -> CacheStats:
        return CacheStats(hits=0, misses=0, entries=0)


def test_backend_errors_never_propagate(
    monkeypatch: pytest.MonkeyPatch, fake_bundle: Any, stub_bi_encoder: Any
) -> None:
    """`pipeline.cached_match` must degrade to uncached, not fail the request, when
    the cache backend raises on both `get` and `set`."""

    from src.talentrank import pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "get_cache_backend", lambda: _BrokenBackend())

    response = pipeline_module.cached_match("x" * 50, top_k=5, top_n=3, bundle=fake_bundle)

    assert response.cached is False
    assert response.results
