"""API-level tests for `/auth/*`. See .claude/enhancements/20-authentication-backend.md.

Uses `async_client` (httpx.AsyncClient over ASGITransport, real `db_session`) rather
than the sync `client` fixture -- see `conftest.py`'s docstrings on both for why the
`/auth` endpoints, which touch a real async DB session, need the former.
"""

from __future__ import annotations

import httpx
import pytest

from src.talentrank.config import get_settings

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
