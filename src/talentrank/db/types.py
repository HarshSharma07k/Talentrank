"""Cross-dialect timestamp handling. See enhancements/19."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class TZDateTime(TypeDecorator[datetime]):
    """A timestamp that is timezone-aware UTC on both SQLite and PostgreSQL.

    PostgreSQL's `TIMESTAMP WITH TIME ZONE` round-trips an aware `datetime`. SQLite has
    no timezone type at all: it stores an ISO string and hands back a **naive**
    `datetime`. Comparing a naive value against an aware one raises `TypeError`, and
    comparing two naive values that were written in different zones is silently wrong --
    so every timestamp column in this project uses this type, never a bare `DateTime`.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("TZDateTime requires a timezone-aware datetime; got a naive one.")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    """`datetime.now(timezone.utc)`. Never `datetime.utcnow()` -- that returns naive."""

    return datetime.now(timezone.utc)
