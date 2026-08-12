"""Tests for saved lists and items. See .claude/enhancements/21-user-scoped-data.md.

Service-level tests against `db_session` -- no HTTP.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.config import get_settings
from src.talentrank.db.models import User
from src.talentrank.userdata import lists

pytestmark = pytest.mark.anyio


async def _make_user(db: AsyncSession, email: str) -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


async def test_duplicate_list_name_409(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "dup-list@example.com")
    await lists.create_list(db_session, user, "Shortlist")

    with pytest.raises(lists.DuplicateListNameError):
        await lists.create_list(db_session, user, "Shortlist")


async def test_adding_same_job_twice_is_idempotent(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "idempotent-item@example.com")
    saved_list = await lists.create_list(db_session, user, "Shortlist")

    first, first_created = await lists.add_item(db_session, user, saved_list.id, 1, "Engineer", "ENGINEERING", None)
    second, second_created = await lists.add_item(db_session, user, saved_list.id, 1, "Engineer", "ENGINEERING", None)

    assert first_created is True
    assert second_created is False
    assert first is not None and second is not None
    assert first.id == second.id

    _list, count = (await lists.list_lists(db_session, user))[0]
    assert count == 1


async def test_deleting_list_cascades_to_items(db_session: AsyncSession) -> None:
    import uuid

    from sqlalchemy import select

    from src.talentrank.db.models import SavedListItem

    user = await _make_user(db_session, "cascade-list@example.com")
    saved_list = await lists.create_list(db_session, user, "Shortlist")
    await lists.add_item(db_session, user, saved_list.id, 1, "Engineer", "ENGINEERING", None)

    deleted = await lists.delete_list(db_session, user, saved_list.id)
    assert deleted is True

    remaining = (
        (await db_session.execute(select(SavedListItem).where(SavedListItem.saved_list_id == saved_list.id)))
        .scalars()
        .all()
    )
    assert remaining == []
    assert await lists.get_list(db_session, user, uuid.UUID(str(saved_list.id))) is None


async def test_list_quota_returns_409_not_silent_drop(db_session: AsyncSession) -> None:
    settings = get_settings()
    settings.max_saved_lists_per_user = 2

    user = await _make_user(db_session, "list-quota@example.com")
    await lists.create_list(db_session, user, "List A")
    await lists.create_list(db_session, user, "List B")

    with pytest.raises(lists.ListQuotaExceededError):
        await lists.create_list(db_session, user, "List C")


async def test_item_quota_returns_409_not_silent_drop(db_session: AsyncSession) -> None:
    settings = get_settings()
    settings.max_items_per_saved_list = 2

    user = await _make_user(db_session, "item-quota@example.com")
    saved_list = await lists.create_list(db_session, user, "Shortlist")
    await lists.add_item(db_session, user, saved_list.id, 1, "A", "OTHER", None)
    await lists.add_item(db_session, user, saved_list.id, 2, "B", "OTHER", None)

    with pytest.raises(lists.ItemQuotaExceededError):
        await lists.add_item(db_session, user, saved_list.id, 3, "C", "OTHER", None)


async def test_lists_scoped_to_owner(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "list-owner@example.com")
    other = await _make_user(db_session, "list-other@example.com")

    saved_list = await lists.create_list(db_session, owner, "Shortlist")

    assert await lists.get_list(db_session, other, saved_list.id) is None
    assert await lists.rename_list(db_session, other, saved_list.id, "Hijacked") is None
    assert await lists.delete_list(db_session, other, saved_list.id) is False
    item, _created = await lists.add_item(db_session, other, saved_list.id, 1, "X", "OTHER", None)
    assert item is None
    assert await lists.remove_item(db_session, other, saved_list.id, 1) is False

    assert await lists.get_list(db_session, owner, saved_list.id) is not None
