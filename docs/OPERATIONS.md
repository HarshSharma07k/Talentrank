# Operations

Runbook for the persistence/auth arc (enhancements/19–24). Written for whoever is
running this service, including future-you.

## Running a migration

Migrations run automatically, once, before the app server starts —
`docker-entrypoint.sh` runs `python -m alembic upgrade head` and only then
`exec`s gunicorn. **Never run a migration from FastAPI's own `lifespan`**: with
more than one worker process, every worker would race the same migration; the
entrypoint runs exactly once, before any worker exists.

To run one by hand (e.g. against a database the container isn't currently
pointed at):

```bash
TALENTRANK_DATABASE_URL="postgresql+asyncpg://user:password@host:5432/db" \
  python -m alembic upgrade head
```

`alembic.ini`'s own `sqlalchemy.url` is deliberately left blank — `migrations/env.py`
reads the real URL from `get_settings()`, so this one env var is the only thing
that needs to change between environments.

**A rollback does not undo a migration.** Redeploying an older image against an
already-migrated database is how an outage becomes a data-loss event. Any schema
change that needs to be reversible needs its own downgrade migration, written and
tested before it ships, not improvised after the fact.

CI's `migration-drift` job (`.github/workflows/ci.yml`) applies every migration to
a scratch SQLite database and runs `alembic check` against it — a model changed in
`src/talentrank/db/models.py` with no matching migration file fails that job
loudly, rather than silently diverging from what `migrations/versions/` describes.

## Rotating the database credential

1. Create the new credential on the database provider (a new Postgres role, or a
   password reset on the existing one — whichever the provider supports without
   downtime).
2. Update `TALENTRANK_DATABASE_URL` wherever it's set as a secret (the Hugging
   Face Space's secret, not `README.md` front-matter, which is public; the
   deployment's own `.env`, never committed).
3. Restart the API process. `get_engine()` is a process-wide `@lru_cache`
   singleton (`src/talentrank/db/session.py`) — it does not pick up a changed
   `TALENTRANK_DATABASE_URL` without a restart.
4. Revoke the old credential once the new one is confirmed working.

`TALENTRANK_DATABASE_ECHO` must stay `false` in any environment carrying real
data — it logs SQL parameter values, which would put user emails and resume text
into the log stream.

## When a user asks for their data to be deleted

`DELETE /auth/me` (current password required) is the supported path — it is
irreversible and cascades to every table via the database's own
`ON DELETE CASCADE`: `sessions`, `match_runs` (and, through it, any
`match_feedback` tied to a run), `saved_lists` (and, through it,
`saved_list_items`), and any `match_feedback` not tied to a run. There is no
"soft delete" and no recovery window — the account row is gone after that one
call returns `204`.

If a user asks by email rather than through the app (support request, GDPR-style
request), there is currently no admin endpoint for this — connect to the
database directly and delete the matching `users` row; the same cascade applies
regardless of how the delete happens, since it is enforced at the database
level, not in application code.

## What is lost if the database is lost

Everything except the job corpus, which is derived data rebuildable from
`scripts/` (`prep_data.py`, `build_index.py`, `build_demo_corpus.py`,
`build_explain_assets.py`) and was never stored in this database to begin with.

Lost with the database: every account, every session (all users signed out),
every saved match run, every saved list, every relevance-feedback signal. There
is no separate backup of any of this beyond whatever backup/point-in-time-
recovery the database provider itself offers — Postgres on Hugging Face Spaces
is **not** durable storage (the Space's own filesystem is ephemeral and resets
on restart/rebuild/idle), which is exactly why the hosted demo points at a
managed Postgres provider (Neon or Supabase's free tier) instead of the
Space's local disk. Local development and CI use SQLite, which is expected to
be disposable.

## Session cleanup

Session rows accumulate one per login and are never cleaned up automatically —
`enhancements/20` deliberately left this out, and `enhancements/24` added the
job rather than a background task inside the API process (a periodic job
competes with request handling for the one thing this single-worker service is
short of):

```bash
python scripts/maintenance.py --purge-sessions
# also delete sessions revoked more than N days ago (default 30):
python scripts/maintenance.py --purge-sessions --revoked-retention-days 14
```

Run this on a schedule (cron, a scheduled CI job, a platform's own scheduled-task
feature) against the same database the API uses. It is idempotent and safe to
run concurrently with the API serving traffic — it only ever deletes sessions
that are already expired or already revoked, in bounded batches
(`TALENTRANK_SESSION_PURGE_BATCH_SIZE`, default 1000) so a large backlog never
holds one long transaction against a table the API reads on every authenticated
request.

## Local Docker Postgres

`docker compose up` requires `POSTGRES_PASSWORD` set (via `.env`, copied from
`.env.example`) — there is no default, deliberately, so a real deployment can
never silently inherit a guessable placeholder. `docker compose down -v` drops
the `postgres_data` named volume along with everything in it; a plain
`docker compose down` (no `-v`) keeps it, so accounts survive a restart or a
`down && up`.

## Auth traffic and logging

`RequestLoggingMiddleware` (`src/talentrank/middleware.py`) logs exactly
`request_id`, `method`, `path`, `status`, and `took_ms` per request — never a
header and never a body, so no bearer token, password, or resume text reaches
the log stream regardless of which endpoint is called. Any change to this
middleware that adds a new logged field must be checked against this invariant
before it ships.
