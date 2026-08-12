"""Engine, sessionmaker, and the `get_db` FastAPI dependency. See enhancements/19.

`@lru_cache` getters, not lifespan globals: `tests/conftest.py`'s `client` fixture
constructs `TestClient(app)` as a plain instance, **not** as a context manager, so
`lifespan` never runs under the test suite. An engine that only exists after
lifespan would be `None` in every single test. Getters make the engine lazily
available in both worlds, and they are the pattern this codebase already uses
three times (`get_settings`, `get_model_bundle`, `get_cache_backend`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.talentrank.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Process-wide async engine. Dialect-specific pooling is decided here:
    SQLite gets no pool sizing (its driver is not pooled the same way), PostgreSQL
    gets `pool_size` / `max_overflow` / `pool_recycle` from settings."""

    settings = get_settings()
    assert settings.database_url is not None  # always derived by config._derive_paths
    url = settings.database_url.get_secret_value()

    engine_kwargs: dict[str, object] = {"echo": settings.database_echo}
    is_sqlite = url.startswith("sqlite")
    if not is_sqlite:
        engine_kwargs["pool_size"] = settings.database_pool_size
        engine_kwargs["max_overflow"] = settings.database_max_overflow
        engine_kwargs["pool_recycle"] = settings.database_pool_recycle_seconds

    engine = create_async_engine(url, **engine_kwargs)

    if is_sqlite:
        # SQLite ignores foreign keys unless told otherwise per-connection. Without
        # this, cascades appear to work through the ORM (which issues its own DELETE
        # statements) while doing nothing at the DB level -- see
        # test_deleting_user_cascades_to_sessions_and_runs, which proves this pragma
        # is wired by deleting via raw SQL rather than through the ORM's own cascade.
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: object, connection_record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """`async_sessionmaker(get_engine(), expire_on_commit=False)`.

    `expire_on_commit=False` matters: with the default, every attribute of an object
    returned from a committed session triggers a lazy refresh, which on an async
    session raises `MissingGreenlet` rather than quietly issuing a query. Response
    models read attributes after commit, so this must be off.
    """

    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Commits on clean exit, rolls back on any exception, always
    closes. Route handlers must not commit themselves."""

    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
