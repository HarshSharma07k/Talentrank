"""Tests proving Alembic migrations and the ORM agree. See enhancements/19.

Plain sync tests, not `@pytest.mark.anyio`: `alembic.command.upgrade` runs
`migrations/env.py` in-process, which itself calls `asyncio.run(...)` -- that
raises if invoked from inside an already-running event loop, which an anyio-async
test would be.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
import pytest
import sqlalchemy as sa

from src.talentrank.config import get_settings
from src.talentrank.db import models  # noqa: F401 -- registers all six tables on Base.metadata
from src.talentrank.db.base import Base

REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture
def tmp_sqlite_urls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """Points `get_settings().database_url` (what `migrations/env.py` reads) at a
    fresh file under `tmp_path`. Returns `(async_url, sync_url)` -- migrations run
    async, but `compare_metadata` below needs a plain sync `Connection`."""

    db_path = tmp_path / "alembic_test.db"
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    sync_url = f"sqlite:///{db_path.as_posix()}"

    monkeypatch.setenv("TALENTRANK_DATABASE_URL", async_url)
    get_settings.cache_clear()

    return async_url, sync_url


def test_upgrade_head_on_sqlite(tmp_sqlite_urls: tuple[str, str]) -> None:
    command.upgrade(_alembic_config(), "head")


def test_no_autogenerate_drift(tmp_sqlite_urls: tuple[str, str]) -> None:
    _async_url, sync_url = tmp_sqlite_urls
    command.upgrade(_alembic_config(), "head")

    engine = sa.create_engine(sync_url)
    try:
        with engine.connect() as connection:
            migration_context = MigrationContext.configure(
                connection, opts={"compare_type": True, "render_as_batch": True}
            )
            diff = compare_metadata(migration_context, Base.metadata)
    finally:
        engine.dispose()

    assert diff == [], f"Unexpected autogenerate drift: {diff}"
