"""API-level tests for `/auth/*`. See .claude/enhancements/20-authentication-backend.md.

Uses `async_client` (httpx.AsyncClient over ASGITransport, real `db_session`) rather
than the sync `client` fixture -- see `conftest.py`'s docstrings on both for why the
`/auth` endpoints, which touch a real async DB session, need the former.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.talentrank.config import get_settings
from src.talentrank.db.models import MatchFeedback, MatchRun, SavedList, SavedListItem
from src.talentrank.db.models import Session as DBSession
from src.talentrank.db.models import User

pytestmark = pytest.mark.anyio

MIN_RESUME_CHARS = 40


async def _register(
    client: httpx.AsyncClient, email: str = "user@example.com", password: str = "correct-horse-battery"
) -> httpx.Response:
    return await client.post("/auth/register", json={"email": email, "password": password})


async def test_register_then_login_then_me(async_client: httpx.AsyncClient) -> None:
    register_response = await _register(async_client, "person@example.com", "correct-horse-battery")
    assert register_response.status_code == 201
    register_body = register_response.json()
    assert register_body["user"]["email"] == "person@example.com"

    login_response = await async_client.post(
        "/auth/login", json={"email": "person@example.com", "password": "correct-horse-battery"}
    )
    assert login_response.status_code == 200
    login_body = login_response.json()
    assert login_body["token"] != register_body["token"]  # a distinct session, not a reused one

    me_response = await async_client.get("/auth/me", headers={"Authorization": f"Bearer {login_body['token']}"})
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "person@example.com"


async def test_login_wrong_password_401(async_client: httpx.AsyncClient) -> None:
    await _register(async_client, "wrongpw@example.com", "correct-horse-battery")

    response = await async_client.post("/auth/login", json={"email": "wrongpw@example.com", "password": "not-it"})

    assert response.status_code == 401


async def test_me_without_token_401_with_www_authenticate(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_me_with_garbage_token_401(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/auth/me", headers={"Authorization": "Bearer this-token-does-not-exist"})

    assert response.status_code == 401


async def test_logout_invalidates_token(async_client: httpx.AsyncClient) -> None:
    register_response = await _register(async_client, "logout@example.com", "correct-horse-battery")
    token = register_response.json()["token"]

    logout_response = await async_client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_response.status_code == 204

    me_response = await async_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 401


async def test_register_disabled_returns_403(async_client: httpx.AsyncClient) -> None:
    get_settings().auth_registration_enabled = False

    response = await _register(async_client, "disabled@example.com", "correct-horse-battery")

    assert response.status_code == 403


async def test_auth_endpoints_rate_limited(async_client: httpx.AsyncClient) -> None:
    """Mutates the settings singleton in place, mirroring the existing
    `test_api.py::test_rate_limit_429` pattern."""

    settings = get_settings()
    settings.auth_rate_limit_requests = 2
    settings.auth_rate_limit_window_seconds = 60

    responses = [
        await async_client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever12345"})
        for _ in range(3)
    ]

    assert [r.status_code for r in responses] == [401, 401, 429]
    assert responses[-1].headers["retry-after"] == "60"


async def test_user_response_never_contains_password_hash(async_client: httpx.AsyncClient) -> None:
    response = await _register(async_client, "nohash@example.com", "correct-horse-battery")

    assert "password_hash" not in response.text
    body = response.json()
    assert "password_hash" not in body["user"]


async def test_anonymous_match_still_works(async_client: httpx.AsyncClient) -> None:
    """The regression guard for this whole document: /match with no Authorization
    header must behave exactly as it did before enhancements/20."""

    response = await async_client.post("/match", json={"resume_text": "x" * MIN_RESUME_CHARS})

    assert response.status_code == 200


async def test_match_with_invalid_bearer_token_still_401s_not_500s(async_client: httpx.AsyncClient) -> None:
    """/match itself is not wired to any auth dependency in this document -- doing
    so would violate its own hard constraint ("do not make any currently public
    endpoint require authentication"). So an invalid bearer token here is never
    resolved by application code at all; the only real regression risk is the
    RateLimitMiddleware's token-bucketing logic (enhancements/20) choking on a
    garbage token and 500ing. It must not -- the request proceeds exactly as an
    anonymous one would.
    """

    response = await async_client.post(
        "/match",
        json={"resume_text": "x" * MIN_RESUME_CHARS},
        headers={"Authorization": "Bearer this-is-not-a-real-token"},
    )

    assert response.status_code == 200


# --- Account deletion (enhancements/24) -----------------------------------------


async def test_delete_account_requires_current_password(async_client: httpx.AsyncClient) -> None:
    register_response = await _register(async_client, "delete-wrong-pw@example.com", "correct-horse-battery")
    token = register_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = await async_client.request("DELETE", "/auth/me", json={"current_password": "not-it"}, headers=headers)
    assert response.status_code == 401

    # A wrong password must not delete anything -- the account still authenticates.
    me_response = await async_client.get("/auth/me", headers=headers)
    assert me_response.status_code == 200


async def test_deleting_account_removes_all_user_rows(
    async_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """Asserts emptiness in every one of enhancements/19's six tables by name --
    a test that checks three of six passes while leaving personal data behind."""

    register_response = await _register(async_client, "delete-cascade@example.com", "correct-horse-battery")
    token = register_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = uuid.UUID(register_response.json()["user"]["id"])

    match_response = await async_client.post("/match", json={"resume_text": "x" * MIN_RESUME_CHARS}, headers=headers)
    assert match_response.status_code == 200
    match_body = match_response.json()
    run_id = match_body["run_id"]
    assert run_id is not None
    assert match_body["results"], "fixture jobs frame must produce at least one result"
    job_id = match_body["results"][0]["job_id"]

    feedback_response = await async_client.post(
        "/me/feedback",
        json={"job_id": job_id, "signal": "up", "rank": 1, "resume_hash": match_body["resume_hash"], "run_id": run_id},
        headers=headers,
    )
    assert feedback_response.status_code == 201

    list_response = await async_client.post("/me/lists", json={"name": "Test list"}, headers=headers)
    assert list_response.status_code == 201
    list_id = list_response.json()["id"]
    item_response = await async_client.post(
        f"/me/lists/{list_id}/items",
        json={"job_id": job_id, "job_title": "Some Title", "job_family": "OTHER"},
        headers=headers,
    )
    assert item_response.status_code == 201

    delete_response = await async_client.request(
        "DELETE", "/auth/me", json={"current_password": "correct-horse-battery"}, headers=headers
    )
    assert delete_response.status_code == 204

    assert (await db_session.execute(select(User).where(User.id == user_id))).scalar_one_or_none() is None
    assert (await db_session.execute(select(DBSession).where(DBSession.user_id == user_id))).first() is None
    assert (await db_session.execute(select(MatchRun).where(MatchRun.user_id == user_id))).first() is None
    assert (await db_session.execute(select(SavedList).where(SavedList.user_id == user_id))).first() is None
    assert (await db_session.execute(select(SavedListItem))).first() is None  # only list in this test's session
    assert (await db_session.execute(select(MatchFeedback).where(MatchFeedback.user_id == user_id))).first() is None


async def test_deleted_account_token_no_longer_authenticates(async_client: httpx.AsyncClient) -> None:
    register_response = await _register(async_client, "delete-token@example.com", "correct-horse-battery")
    token = register_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    delete_response = await async_client.request(
        "DELETE", "/auth/me", json={"current_password": "correct-horse-battery"}, headers=headers
    )
    assert delete_response.status_code == 204

    me_response = await async_client.get("/auth/me", headers=headers)
    assert me_response.status_code == 401
