"""Password hashing. See enhancements/20.

Argon2id, not the wrong-tool choice on the other side of this module
(`auth/tokens.py`'s SHA-256): a password is low-entropy and human-chosen, so it
needs a deliberately slow, memory-hard KDF to make offline guessing expensive.
"""

from __future__ import annotations

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from src.talentrank.config import get_settings


@lru_cache(maxsize=1)
def get_password_hasher() -> PasswordHasher:
    """Argon2id hasher configured from settings.

    Defaults are OWASP's second recommended profile (m=19456 KiB, t=2, p=1) -- a
    published recommendation, cited as such, not a value measured by this project.
    They are deliberately not the library defaults (m=65536 KiB): this service runs
    on 2 vCPU with `max_request_threads=8`, so eight concurrent logins at 64 MiB
    each would be 512 MiB of transient allocation on a box that also holds two
    models.
    """

    settings = get_settings()
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost_kib,
        parallelism=settings.argon2_parallelism,
    )


def hash_password(password: str) -> str:
    """Return an Argon2id encoded hash string (includes algorithm, params, salt)."""

    return get_password_hasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-time-ish verify. Returns False rather than raising on a bad hash."""

    try:
        return get_password_hasher().verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when `password_hash` was produced with weaker-than-configured params."""

    return get_password_hasher().check_needs_rehash(password_hash)


# A hash of a throwaway password, computed once at import. Verified against when
# the email is unknown, so a login attempt costs the same wall time whether or not
# the account exists. Without this, response latency is an account-existence
# oracle and enumeration is trivial regardless of what the response body says.
DUMMY_HASH: str = hash_password("dummy-password-never-used-anywhere-else")
