"""In-process and Redis-backed result caching for TalentRank. See enhancements/07.

Used from exactly one call site -- `pipeline.cached_match()`. Both `get` and `set`
are guarded with `try/except` there, so a backend outage degrades the service to
slow, never to a 500.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
import logging
import threading
import time
from typing import Protocol

from src.talentrank.config import get_settings

logger = logging.getLogger("talentrank.cache")
if not logger.handlers:
    # See api.py's identical block: a scoped handler + propagate=False keeps this
    # visible without raising the root logger's level.
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


@dataclass(slots=True)
class CacheStats:
    """Point-in-time counters for a cache backend."""

    hits: int
    misses: int
    entries: int


class CacheBackend(Protocol):
    # The backend actually in use, not the configured setting -- see
    # get_cache_backend()'s docstring on why those two can differ. `/health`'s
    # `cache_backend` field reads this, not `settings.cache_backend`, so a
    # configured-but-unreachable Redis is reported honestly (enhancements/14).
    name: str

    def get(self, key: str) -> bytes | None: ...
    def set(self, key: str, value: bytes, ttl_seconds: int) -> None: ...
    def stats(self) -> CacheStats: ...


class InMemoryTTLCache:
    """LRU + TTL cache. Stdlib only: `OrderedDict` + `threading.Lock`.

    Eviction happens on `set`, so a cache that is only ever read (never written)
    will not proactively expire entries -- acceptable here since the only writer,
    `pipeline.cached_match`, reads immediately before it writes.
    """

    name = "memory"

    def __init__(self, max_entries: int = 256) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._store: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> bytes | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            expires_at, value = entry
            if expires_at < time.monotonic():
                del self._store[key]
                self._misses += 1
                return None

            self._store.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + ttl_seconds, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(hits=self._hits, misses=self._misses, entries=len(self._store))


class RedisCache:
    """Redis-backed cache behind the same `CacheBackend` protocol.

    `redis` is an optional extra -- imported lazily inside `__init__` so a missing
    package never breaks startup in the default (in-memory) configuration.
    """

    name = "redis"

    def __init__(self, url: str) -> None:
        import redis  # local import: optional dependency, see class docstring

        self._client = redis.Redis.from_url(url)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> bytes | None:
        value = self._client.get(key)
        with self._lock:
            if value is None:
                self._misses += 1
            else:
                self._hits += 1
        return value

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        self._client.set(key, value, ex=ttl_seconds)

    def stats(self) -> CacheStats:
        with self._lock:
            hits, misses = self._hits, self._misses
        return CacheStats(hits=hits, misses=misses, entries=int(self._client.dbsize()))


@lru_cache(maxsize=1)
def get_cache_backend() -> CacheBackend:
    """Return the process-wide cache backend singleton, per `settings.cache_backend`.

    A Redis connection failure at construction time degrades to in-memory rather
    than failing startup -- logged once at warning level, not per request. This is
    exactly why `/health.cache_backend` must read `get_cache_backend().name`
    rather than `settings.cache_backend`: the latter is the configured intent,
    but a Redis outage silently substitutes a different object here, and a health
    check that reports the former would lie about which backend requests are
    actually hitting.
    """

    settings = get_settings()
    if settings.cache_backend == "redis" and settings.redis_url:
        try:
            backend = RedisCache(settings.redis_url)
            backend._client.ping()
            return backend
        except Exception:
            logger.warning("Redis cache backend unavailable; falling back to in-memory.")

    return InMemoryTTLCache(max_entries=settings.cache_max_entries)
