"""Session bearer tokens. See enhancements/20.

Why the token is hashed with SHA-256 and not Argon2, the inverse of the password
decision one file over: a password is low-entropy and human-chosen, so it needs a
deliberately slow KDF to make guessing expensive. A session token is 256 uniformly
random bits -- there is nothing to guess, so the only job of the hash is to make a
database dump useless to an attacker. Running Argon2 on every authenticated request
instead would add tens of milliseconds to a p50 that enhancements/08 spent an
entire document reducing from 666.1 ms to 138.7 ms.

The lookup is by `token_hash` (a `UNIQUE` indexed column), so it is a single index
hit, not a scan-and-compare -- which is also why the token can be hashed rather
than encrypted.
"""

from __future__ import annotations

import hashlib
import secrets

from src.talentrank.config import get_settings


def mint_session_token() -> tuple[str, str]:
    """Return `(token, token_hash)`.

    `secrets.token_urlsafe(settings.session_token_bytes)` -- 32 bytes, 256 bits of
    entropy by default. The plaintext is returned to the client exactly once and
    never stored.
    """

    token = secrets.token_urlsafe(get_settings().session_token_bytes)
    return token, hash_session_token(token)


def hash_session_token(token: str) -> str:
    """`hashlib.sha256(token.encode()).hexdigest()` -- 64 hex chars."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()
