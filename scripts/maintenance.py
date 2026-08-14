"""Operational maintenance CLI. See enhancements/24.

    python scripts/maintenance.py --purge-sessions

A periodic job (cron, a manual invocation, a scheduled CI run) -- deliberately
not a background task inside the API process, and never exposed as an HTTP
endpoint. See `src.talentrank.maintenance.purge_expired_sessions`'s own
docstring for why.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.talentrank.db.session import get_sessionmaker  # noqa: E402
from src.talentrank.maintenance import purge_expired_sessions  # noqa: E402

# Not a Settings field (enhancements/24's own "Config keys added" list has only
# TALENTRANK_SESSION_PURGE_BATCH_SIZE) -- this is an operator-facing CLI choice
# about how long to keep an already-revoked session row around, not a runtime
# behaviour the API itself needs to know.
DEFAULT_REVOKED_RETENTION_DAYS = 30


async def _run_purge_sessions(revoked_retention_days: int) -> None:
    older_than = datetime.now(timezone.utc) - timedelta(days=revoked_retention_days)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        deleted = await purge_expired_sessions(db, older_than)
        await db.commit()
    print(f"Purged {deleted} session row(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--purge-sessions", action="store_true", help="Delete expired sessions and stale revoked sessions."
    )
    parser.add_argument(
        "--revoked-retention-days",
        type=int,
        default=DEFAULT_REVOKED_RETENTION_DAYS,
        help="Also delete sessions revoked more than this many days ago (default: %(default)s).",
    )
    args = parser.parse_args()

    if not args.purge_sessions:
        parser.print_help()
        return

    asyncio.run(_run_purge_sessions(args.revoked_retention_days))


if __name__ == "__main__":
    main()
