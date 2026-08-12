"""Saved lists and items. See enhancements/21."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.config import get_settings
from src.talentrank.db.models import SavedList, SavedListItem, User


class DuplicateListNameError(Exception):
    """Raised by `create_list`/`rename_list` on a name collision for this user."""


class ListQuotaExceededError(Exception):
    """Raised by `create_list` at `settings.max_saved_lists_per_user`. 409, not a
    silent drop -- the user named this thing."""


class ItemQuotaExceededError(Exception):
    """Raised by `add_item` at `settings.max_items_per_saved_list`. 409."""


async def create_list(db: AsyncSession, user: User, name: str) -> SavedList:
    settings = get_settings()
    count = (
        await db.execute(select(func.count()).select_from(SavedList).where(SavedList.user_id == user.id))
    ).scalar_one()
    if count >= settings.max_saved_lists_per_user:
        raise ListQuotaExceededError()

    saved_list = SavedList(user_id=user.id, name=name)
    db.add(saved_list)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateListNameError(name) from exc
    return saved_list


async def list_lists(db: AsyncSession, user: User) -> list[tuple[SavedList, int]]:
    """Every list this user owns, paired with its item count -- two queries total,
    not one-plus-N: a single grouped count query, merged with the list rows in
    Python."""

    lists_result = await db.execute(
        select(SavedList).where(SavedList.user_id == user.id).order_by(SavedList.created_at.desc())
    )
    lists = list(lists_result.scalars().all())
    if not lists:
        return []

    counts_result = await db.execute(
        select(SavedListItem.saved_list_id, func.count())
        .where(SavedListItem.saved_list_id.in_([lst.id for lst in lists]))
        .group_by(SavedListItem.saved_list_id)
    )
    counts = dict(counts_result.all())

    return [(lst, counts.get(lst.id, 0)) for lst in lists]


async def get_list(db: AsyncSession, user: User, list_id: uuid.UUID) -> SavedList | None:
    """Ownership enforced in the query -- see enhancements/21's own note on why
    (never fetch by id then compare `row.user_id` in Python)."""

    result = await db.execute(select(SavedList).where(SavedList.id == list_id, SavedList.user_id == user.id))
    return result.scalar_one_or_none()


async def list_items(db: AsyncSession, saved_list: SavedList) -> list[SavedListItem]:
    """A standalone query, not `saved_list.items` -- accessing a lazy relationship
    on an async session without eager loading raises `MissingGreenlet` (see
    enhancements/19's own note on `expire_on_commit=False` and lazy loads)."""

    result = await db.execute(
        select(SavedListItem)
        .where(SavedListItem.saved_list_id == saved_list.id)
        .order_by(SavedListItem.created_at.asc())
    )
    return list(result.scalars().all())


async def rename_list(db: AsyncSession, user: User, list_id: uuid.UUID, name: str) -> SavedList | None:
    saved_list = await get_list(db, user, list_id)
    if saved_list is None:
        return None

    saved_list.name = name
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateListNameError(name) from exc
    return saved_list


async def delete_list(db: AsyncSession, user: User, list_id: uuid.UUID) -> bool:
    """A Core bulk `DELETE`, not `db.delete(obj)` -- relies on the DB-level
    `ON DELETE CASCADE` wired in enhancements/19 (`PRAGMA foreign_keys=ON`) to
    remove the list's items, so it works in one round trip regardless of how many
    items the list holds."""

    result = await db.execute(delete(SavedList).where(SavedList.id == list_id, SavedList.user_id == user.id))
    return result.rowcount > 0


async def add_item(
    db: AsyncSession, user: User, list_id: uuid.UUID, job_id: int, job_title: str, job_family: str, note: str | None
) -> tuple[SavedListItem | None, bool]:
    """Returns `(item, created)`. `item` is `None` when the list doesn't exist or
    isn't owned by `user` -- the router 404s on that. `created=False` means the
    item was already present (an idempotent no-op, router responds 200); `True`
    means a new row was inserted (router responds 201).
    """

    saved_list = await get_list(db, user, list_id)
    if saved_list is None:
        return None, False

    existing_result = await db.execute(
        select(SavedListItem).where(SavedListItem.saved_list_id == saved_list.id, SavedListItem.job_id == job_id)
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    settings = get_settings()
    item_count = (
        await db.execute(
            select(func.count()).select_from(SavedListItem).where(SavedListItem.saved_list_id == saved_list.id)
        )
    ).scalar_one()
    if item_count >= settings.max_items_per_saved_list:
        raise ItemQuotaExceededError()

    item = SavedListItem(
        saved_list_id=saved_list.id, job_id=job_id, job_title=job_title, job_family=job_family, note=note
    )
    db.add(item)
    await db.flush()
    return item, True


async def remove_item(db: AsyncSession, user: User, list_id: uuid.UUID, job_id: int) -> bool:
    saved_list = await get_list(db, user, list_id)
    if saved_list is None:
        return False

    result = await db.execute(
        delete(SavedListItem).where(SavedListItem.saved_list_id == saved_list.id, SavedListItem.job_id == job_id)
    )
    return result.rowcount > 0
