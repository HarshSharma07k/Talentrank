"""The `/auth` APIRouter. See enhancements/20."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.auth import service
from src.talentrank.auth.deps import auth_rate_limiter, get_current_user, get_current_user_and_token
from src.talentrank.auth.schemas import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    LoginRequest,
    RegisterRequest,
    SessionResponse,
    SessionSummary,
    UpdateProfileRequest,
    UserResponse,
)
from src.talentrank.config import get_settings
from src.talentrank.db.models import Session as DBSession
from src.talentrank.db.models import User
from src.talentrank.db.session import get_db

# Every route on this router carries auth_rate_limiter -- a strict per-IP limiter
# scoped to credential endpoints, separate from the general RateLimitMiddleware.
router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(auth_rate_limiter)])


def _session_response(token: str, session_row: DBSession, user: User) -> SessionResponse:
    return SessionResponse(token=token, expires_at=session_row.expires_at, user=UserResponse.from_user(user))


@router.post("/register", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)) -> SessionResponse:
    settings = get_settings()
    if not settings.auth_registration_enabled:
        raise HTTPException(status_code=403, detail="Registration is currently disabled.")

    try:
        user = await service.register_user(db, body.email, body.password, body.display_name)
    except service.EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc

    token, session_row = await service.create_session(db, user, request.headers.get("user-agent"))
    return _session_response(token, session_row, user)


@router.post("/login", response_model=SessionResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> SessionResponse:
    user = await service.authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token, session_row = await service.create_session(db, user, request.headers.get("user-agent"))
    return _session_response(token, session_row, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    user_and_token: tuple[User, str] = Depends(get_current_user_and_token), db: AsyncSession = Depends(get_db)
) -> None:
    _user, token = user_and_token
    await service.revoke_session(db, token)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    await service.revoke_all_sessions(db, user)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.from_user(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UpdateProfileRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> UserResponse:
    user.display_name = body.display_name
    await db.flush()
    return UserResponse.from_user(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    user_and_token: tuple[User, str] = Depends(get_current_user_and_token),
    db: AsyncSession = Depends(get_db),
) -> None:
    user, token = user_and_token
    try:
        await service.change_password(db, user, body.current_password, body.new_password, token)
    except service.InvalidCurrentPasswordError as exc:
        raise HTTPException(status_code=401, detail="Current password is incorrect.") from exc


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: DeleteAccountRequest,
    user_and_token: tuple[User, str] = Depends(get_current_user_and_token),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Irreversible. See enhancements/24 -- `service.delete_account` cascades to
    every child table via `ON DELETE CASCADE`; no explicit session revocation is
    needed here, the caller's own session row is deleted along with the rest."""

    user, _token = user_and_token
    try:
        await service.delete_account(db, user, body.current_password)
    except service.InvalidCurrentPasswordError as exc:
        raise HTTPException(status_code=401, detail="Current password is incorrect.") from exc


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[SessionSummary]:
    result = await db.execute(
        select(DBSession)
        .where(DBSession.user_id == user.id, DBSession.revoked_at.is_(None))
        .order_by(DBSession.created_at.desc())
    )
    return [SessionSummary.from_session(row) for row in result.scalars().all()]
