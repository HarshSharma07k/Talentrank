"""Tests for Argon2id password hashing. See .claude/enhancements/20-authentication-backend.md."""

from __future__ import annotations

import pytest

from src.talentrank.auth.passwords import (
    get_password_hasher,
    hash_password,
    needs_rehash,
    verify_password,
)
from src.talentrank.config import get_settings


def test_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("correct-horse-battery-staple")

    assert verify_password(hashed, "correct-horse-battery-staple") is True


def test_verify_rejects_wrong_password() -> None:
    hashed = hash_password("correct-horse-battery-staple")

    assert verify_password(hashed, "wrong-password") is False


def test_hash_is_salted() -> None:
    first = hash_password("correct-horse-battery-staple")
    second = hash_password("correct-horse-battery-staple")

    assert first != second


def test_needs_rehash_on_weaker_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TALENTRANK_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("TALENTRANK_ARGON2_MEMORY_COST_KIB", "8")
    get_settings.cache_clear()
    get_password_hasher.cache_clear()

    weak_hash = hash_password("correct-horse-battery-staple")

    monkeypatch.setenv("TALENTRANK_ARGON2_TIME_COST", "2")
    monkeypatch.setenv("TALENTRANK_ARGON2_MEMORY_COST_KIB", "19456")
    get_settings.cache_clear()
    get_password_hasher.cache_clear()

    assert needs_rehash(weak_hash) is True


def test_hasher_uses_configured_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TALENTRANK_ARGON2_TIME_COST", "3")
    monkeypatch.setenv("TALENTRANK_ARGON2_MEMORY_COST_KIB", "12288")
    monkeypatch.setenv("TALENTRANK_ARGON2_PARALLELISM", "2")
    get_settings.cache_clear()
    get_password_hasher.cache_clear()

    hasher = get_password_hasher()

    assert hasher.time_cost == 3
    assert hasher.memory_cost == 12288
    assert hasher.parallelism == 2
