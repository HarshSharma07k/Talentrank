"""Registration, authentication, and session lifecycle. See enhancements/20.

Pure `AsyncSession`-in, model-out functions -- no HTTP here. `auth/router.py` is
the only caller that turns these into responses and status codes.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.auth.passwords import DUMMY_HASH, hash_password, needs_rehash, verify_password
from src.talentrank.auth.tokens import hash_session_token, mint_session_token
from src.talentrank.config import get_settings
from src.talentrank.db.models import Session as DBSession
from src.talentrank.db.models import User
from src.talentrank.db.types import utcnow


class EmailAlreadyRegisteredError(Exception):
    """Raised by `register_user` on a duplicate (case-insensitive) email."""


class InvalidCurrentPasswordError(Exception):
    """Raised by `change_password` when `current` does not verify."""


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def register_user(db: AsyncSession, email: str, password: str, display_name: str | None = None) -> User:
    """Raises `EmailAlreadyRegisteredError` on a duplicate. Email is lowercased and
    stripped before storage and lookup, so `A@b.com` and `a@b.com` are one account.

    Relies on the DB's own `UNIQUE` constraint (not a check-then-insert) to close
    the race between two concurrent registrations for the same address.
    """

    user = User(email=_normalize_email(email), password_hash=hash_password(password), display_name=display_name)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise EmailAlreadyRegisteredError(email) from exc

    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    """Returns None for both "no such user" and "wrong password" -- the caller must
    not be able to distinguish them, and neither must the clock. Verifies against
    `DUMMY_HASH` when the user is absent. Transparently rehashes on `needs_rehash`.
    Updates `last_login_at`.
    """

    result = await db.execute(select(User).where(User.email == _normalize_email(email)))
    user = result.scalar_one_or_none()

    if user is None:
        verify_password(DUMMY_HASH, password)  # burn the same wall-clock cost as a real user
        return None

    if not verify_password(user.password_hash, password):
        return None

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_login_at = utcnow()
    await db.flush()
    return user


async def create_session(db: AsyncSession, user: User, user_agent: str | None) -> tuple[str, DBSession]:
    """Mints a token, stores its hash, and prunes the user's oldest sessions down to
    `settings.session_max_per_user`. Returns the plaintext token -- the only time it
    exists.
    """

    settings = get_settings()
    token, token_hash = mint_session_token()
    now = utcnow()

    session_row = DBSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        last_used_at=now,
        user_agent=user_agent[:256] if user_agent else None,
    )
    db.add(session_row)
    await db.flush()

    stale = await db.execute(
        select(DBSession.id)
        .where(DBSession.user_id == user.id)
        .order_by(DBSession.created_at.desc())
        .offset(settings.session_max_per_user)
    )
    stale_ids = [row[0] for row in stale.all()]
    if stale_ids:
        await db.execute(delete(DBSession).where(DBSession.id.in_(stale_ids)))
        await db.flush()

    return token, session_row


async def resolve_session(db: AsyncSession, token: str) -> User | None:
    """Look up by token hash. Returns None if absent, revoked, expired, or the user
    is inactive. Renews `expires_at` only when the session is older than
    `session_sliding_renewal_seconds`, so the common case is a pure read -- a write
    on every authenticated request would make the DB the bottleneck for a read-only
    page.
    """

    result = await db.execute(select(DBSession).where(DBSession.token_hash == hash_session_token(token)))
    session_row = result.scalar_one_or_none()

    now = utcnow()
    if session_row is None or session_row.revoked_at is not None or session_row.expires_at <= now:
        return None

    # A direct primary-key lookup, not `session_row.user` -- accessing a lazy
    # relationship on an async session without eager loading raises
    # `MissingGreenlet` (see enhancements/19's `expire_on_commit=False` note).
    user = await db.get(User, session_row.user_id)
    if user is None or not user.is_active:
        return None

    settings = get_settings()
    if (now - session_row.last_used_at).total_seconds() > settings.session_sliding_renewal_seconds:
        session_row.last_used_at = now
        session_row.expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
        await db.flush()

    return user


async def revoke_session(db: AsyncSession, token: str) -> None:
    result = await db.execute(select(DBSession).where(DBSession.token_hash == hash_session_token(token)))
    session_row = result.scalar_one_or_none()
    if session_row is not None and session_row.revoked_at is None:
        session_row.revoked_at = utcnow()
        await db.flush()


async def revoke_all_sessions(db: AsyncSession, user: User, except_token: str | None = None) -> None:
    stmt = update(DBSession).where(DBSession.user_id == user.id, DBSession.revoked_at.is_(None))
    if except_token is not None:
        stmt = stmt.where(DBSession.token_hash != hash_session_token(except_token))
    await db.execute(stmt.values(revoked_at=utcnow()))
    await db.flush()


async def change_password(db: AsyncSession, user: User, current: str, new: str, current_token: str) -> None:
    """Verifies `current` first, then revokes every session except the caller's own.

    `current_token` is not in enhancements/20's own contract sketch, which omits any
    way to identify "the caller's own" session despite the docstring's claim --
    fixed here as part of this document's own work, per `/next-enhancement`'s "if a
    document contradicts the code, the code is the truth."
    """

    if not verify_password(user.password_hash, current):
        raise InvalidCurrentPasswordError()

    user.password_hash = hash_password(new)
    await db.flush()
    await revoke_all_sessions(db, user, except_token=current_token)
