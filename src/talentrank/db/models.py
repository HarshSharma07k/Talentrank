"""ORM models for the whole accounts/persistence arc. See enhancements/19.

Landing all six tables in one migration, rather than one per consuming document
(`20`-`23`), is deliberate: later documents add no migrations of their own, so
there is exactly one place where the schema is reviewed and exactly one initial
revision to keep in sync.

Conventions applied to every table:

- Primary keys are `uuid.uuid4()`-generated `Uuid` columns. SQLAlchemy's `Uuid`
  renders native `uuid` on PostgreSQL and `CHAR(32)` on SQLite, so no dialect
  branching is needed.
- Every timestamp is `TZDateTime` (`db/types.py`), never a bare `DateTime`.
- Every child foreign key is `ondelete="CASCADE"`, with `cascade="all,
  delete-orphan"` on the parent relationship so the ORM and the DB agree. SQLite
  does not enforce foreign keys unless `PRAGMA foreign_keys=ON` -- see
  `db/session.py`'s connect hook.
- `job_id` is `Integer`, matching the wire type (`schemas.JobMatch.job_id: int`,
  `frontend/src/lib/api.ts`'s `job_id: number`). The in-memory jobs frame is
  indexed by *string* `job_id` inside `models.get_model_bundle`; that is an
  internal pandas detail and must not leak into this schema.
"""

from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Boolean, Float, Uuid

from src.talentrank.db.base import Base
from src.talentrank.db.types import TZDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    sessions: Mapped[list[Session]] = relationship(back_populates="user", cascade="all, delete-orphan")
    match_runs: Mapped[list[MatchRun]] = relationship(back_populates="user", cascade="all, delete-orphan")
    saved_lists: Mapped[list[SavedList]] = relationship(back_populates="user", cascade="all, delete-orphan")
    match_feedback: Mapped[list[MatchFeedback]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    """An opaque bearer session. See enhancements/20 for the token scheme."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, index=True)
    last_used_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(256))
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    user: Mapped[User] = relationship(back_populates="sessions")


class MatchRun(Base):
    """One saved `/match` result -- the server-side successor to enhancements/12's
    localStorage history entry, for signed-in users only."""

    __tablename__ = "match_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    # Exactly the widths pipeline.py already produces: cached_match truncates its
    # SHA-256 to 16 hex chars, _filters_digest to 8. Reuse those two functions
    # rather than recomputing -- a wider column invites a second, subtly different
    # digest to appear later and silently break dedup.
    resume_hash: Mapped[str] = mapped_column(String(16), nullable=False)
    resume_text: Mapped[str] = mapped_column(Text, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    top_n: Mapped[int] = mapped_column(Integer, nullable=False)
    filters: Mapped[dict] = mapped_column(JSON, nullable=False)
    filters_digest: Mapped[str] = mapped_column(String(8), nullable=False)
    results: Mapped[list] = mapped_column(JSON, nullable=False)
    corpus_profile: Mapped[str] = mapped_column(String(16), nullable=False)
    took_ms: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="match_runs")
    feedback: Mapped[list[MatchFeedback]] = relationship(back_populates="match_run", cascade="all, delete-orphan")

    # A plain composite index, not the doc's own `desc("created_at")` sketch: a
    # descending expression index cannot be reliably reflected/compared by
    # SQLite's autogenerate support (confirmed via `alembic check` reporting
    # permanent phantom drift), and a plain B-tree index is scanned just as
    # efficiently in reverse for `ORDER BY created_at DESC` on both SQLite and
    # PostgreSQL, so nothing is actually lost.
    __table_args__ = (Index("ix_match_runs_user_created", "user_id", "created_at"),)


class SavedList(Base):
    __tablename__ = "saved_lists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="saved_lists")
    items: Mapped[list[SavedListItem]] = relationship(back_populates="saved_list", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("user_id", "name"),)


class SavedListItem(Base):
    __tablename__ = "saved_list_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    saved_list_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("saved_lists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Snapshots, not a live join -- there is no `jobs` table. The corpus is a
    # parquet file loaded into ModelBundle and changes wholesale between the
    # `full` and `demo` profiles; a saved item must still render its title when
    # the corpus underneath it is swapped.
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    job_family: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)

    saved_list: Mapped[SavedList] = relationship(back_populates="items")

    __table_args__ = (UniqueConstraint("saved_list_id", "job_id"),)


class MatchFeedback(Base):
    """Relevance signal. The reason enhancements/99 named click-through data as a
    reversal trigger -- this is the only honest path to the learning-to-rank story."""

    __tablename__ = "match_feedback"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("match_runs.id", ondelete="CASCADE"), index=True
    )
    resume_hash: Mapped[str] = mapped_column(String(16), nullable=False)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    signal: Mapped[str] = mapped_column(String(16), nullable=False)
    # The rank at the moment of the signal -- not redundant with match_runs.results.
    # A signal without the position it was given at is unusable for learning-to-rank;
    # position bias is the first thing any such model has to correct for.
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="match_feedback")
    match_run: Mapped[MatchRun | None] = relationship(back_populates="feedback")

    __table_args__ = (UniqueConstraint("user_id", "match_run_id", "job_id", "signal"),)
