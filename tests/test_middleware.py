"""Tests for HTTP middleware. See .claude/enhancements/07 and /20."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.talentrank.config import get_settings


def test_authenticated_requests_bucket_separately_from_ip(client: TestClient) -> None:
    """A well-formed `Authorization: Bearer <token>` header buckets on the token
    hash (`authenticated_rate_limit_requests`), not the caller's IP -- so an
    exhausted anonymous IP bucket does not also block an authenticated request from
    the same client. `RateLimitMiddleware` never validates the token itself; a
    syntactically well-formed bearer value is enough to route into the separate
    bucket, per enhancements/20's own documented trade-off.
    """

    settings = get_settings()
    settings.rate_limit_requests = 1
    settings.authenticated_rate_limit_requests = 5
    settings.rate_limit_window_seconds = 60

    anon_first = client.get("/health")
    anon_second = client.get("/health")
    assert anon_first.status_code == 200
    assert anon_second.status_code == 429  # the IP bucket's single token is spent

    authed = client.get("/health", headers={"Authorization": "Bearer some-well-formed-token"})
    assert authed.status_code == 200  # a distinct bucket, unaffected by the IP one above
