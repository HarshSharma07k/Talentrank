"""Declarative base shared by every ORM model. See enhancements/19."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# SQLite cannot `ALTER` a constraint, so Alembic emulates it by rebuilding the table
# (`render_as_batch=True`, see migrations/env.py) -- which requires every constraint
# to have a name it can reproduce. Without this convention the first migration works
# and the second one fails on an unnamed constraint.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every TalentRank table."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
