"""Request/response models for the `/auth` router. See enhancements/20."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from src.talentrank.config import get_settings
from src.talentrank.db.models import Session as DBSession
from src.talentrank.db.models import User

_settings = get_settings()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=_settings.password_min_chars, max_length=_settings.password_max_chars)
    display_name: str | None = Field(default=None, max_length=80)


class LoginRequest(BaseModel):
    """No `min_length` on `password`: a legacy account's password may predate a
    later policy tightening, and login must still be able to reject it on its own
    merits rather than on shape. `max_length` still applies -- see
    `RegisterRequest`'s DoS note, which is about bounding Argon2's input, not about
    password strength."""

    email: EmailStr
    password: str = Field(max_length=_settings.password_max_chars)


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=_settings.password_max_chars)
    new_password: str = Field(min_length=_settings.password_min_chars, max_length=_settings.password_max_chars)


class DeleteAccountRequest(BaseModel):
    """See enhancements/24. Irreversible -- the current password is required so a
    stolen but still-valid bearer token alone cannot destroy the account."""

    current_password: str = Field(max_length=_settings.password_max_chars)


class UserResponse(BaseModel):
    """Built field by field from a `User` ORM object in `from_user` below -- never
    `from_attributes` over the ORM object directly, which is one renamed column
    away from serializing `password_hash`."""

    id: str
    email: EmailStr
    display_name: str | None
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(id=str(user.id), email=user.email, display_name=user.display_name, created_at=user.created_at)


class SessionResponse(BaseModel):
    token: str  # the only time the plaintext is ever transmitted
    expires_at: datetime
    user: UserResponse


class SessionSummary(BaseModel):
    """One row of `GET /auth/sessions`. Never includes any token or hash."""

    id: str
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime
    user_agent: str | None

    @classmethod
    def from_session(cls, session: DBSession) -> "SessionSummary":
        return cls(
            id=str(session.id),
            created_at=session.created_at,
            expires_at=session.expires_at,
            last_used_at=session.last_used_at,
            user_agent=session.user_agent,
        )
