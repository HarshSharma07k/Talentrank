#!/bin/sh
# See .claude/enhancements/24-operational-hardening.md.
#
# Migrations run here, before the app server starts -- never from FastAPI's own
# `lifespan` (src/talentrank/api.py). With more than one gunicorn worker, running
# `alembic upgrade head` from `lifespan` would mean every worker races the same
# migration; running it once here, before `exec`, means it happens exactly once,
# before any worker process exists to race.
#
# `set -e`: a failed migration must stop the container from starting, not let it
# come up and silently serve requests against a stale or half-migrated schema.
set -e

echo "Running database migrations..."
python -m alembic upgrade head

exec "$@"
