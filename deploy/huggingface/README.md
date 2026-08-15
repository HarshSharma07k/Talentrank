---
title: TalentRank API
emoji: 📊
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# TalentRank API — Hugging Face Space

This is the **Space's own `README.md`** — its YAML front-matter above is what
Hugging Face reads to configure the Space (`sdk: docker`, `app_port: 7860`).
It ships to the Space repo, not the main GitHub repo, which is why this file
lives under `deploy/huggingface/` here rather than at the project root.

Docker Spaces run the container as **uid 1000** with a restrictive,
mostly-read-only root filesystem — the `Dockerfile`'s `useradd -u 1000` /
`chown` (enhancements/14) and the embeddings-cache `mkdir` moving off the
request path (enhancements/07) both exist because of this constraint.

## Why a separate clone, not `git push` from the main repo

The Space is a **separate git remote**. `.gitignore` is a committed file and
therefore shared across every remote a repo has — there is no way to make
`data/demo/` ignored on `origin` (GitHub) but tracked on the Space remote
using the same working tree. Pushing the main repo's `main` branch straight
to the Space would ship code but never ship the demo corpus the API needs to
serve anything.

The fix used here: maintain a **second, independent local clone** of the
Space's own git repo, and copy the built artifacts into it by hand (or by
script) before each push. This is fiddlier than one `git push`, which is
exactly why it's written out step by step below instead of trusted to memory
in three months.

**Alternative, noted but not used by default:** push `data/demo/` to a
separate Hugging Face **Dataset** repo instead, and have the Docker build
stage `huggingface-cli download` it during the image build. This keeps the
Space repo itself small and avoids LFS entirely in the Space clone. Worth
switching to if `data/demo/` grows past what git-lfs comfortably handles —
today it's ~77 MiB (`jobs_demo.parquet` + `jobs_demo.faiss*`), which LFS
handles fine.

## One-time setup

```bash
# 1. Log in (paste a Hugging Face access token with write scope, from
#    https://huggingface.co/settings/tokens). Never commit this token.
hf auth login

# 2. Create the Space (Docker SDK, free CPU tier). --space-sdk docker matches
#    this repo's own Dockerfile; there is no separate app.py to write.
hf repos create talentrank --type space --space-sdk docker --flavor cpu-basic --sleep-time -1

# 3. Clone the new Space repo somewhere OUTSIDE the main TalentRank working
#    tree, so its own .gitignore and git-lfs config never interact with
#    the main repo's.
git clone https://huggingface.co/spaces/<hf-username>/talentrank ../talentrank-space
cd ../talentrank-space

# 4. git-lfs for the demo corpus artifacts. Do this before the first copy +
#    commit that includes them, or they'll be committed as regular (large)
#    git objects instead.
git lfs install
git lfs track "data/demo/*"
git add .gitattributes
git commit -m "Track data/demo/ with git-lfs"
```

## Every push after that

Run from the main TalentRank repo, copying into the Space clone:

```bash
SPACE_DIR=../talentrank-space   # adjust to wherever you cloned it

# Code + build inputs
rm -rf "$SPACE_DIR/src" "$SPACE_DIR/scripts"
cp -r src "$SPACE_DIR/src"
cp -r scripts "$SPACE_DIR/scripts"
cp Dockerfile requirements.txt alembic.ini docker-entrypoint.sh "$SPACE_DIR/"
cp -r migrations "$SPACE_DIR/migrations"

# Demo corpus + the one full-corpus file the demo profile still needs
# (config.py's Settings._derive_paths keeps term_idf_path on data/processed/
# regardless of corpus_profile -- see the Dockerfile's own comment).
mkdir -p "$SPACE_DIR/data/demo" "$SPACE_DIR/data/processed"
cp data/demo/jobs_demo.parquet data/demo/jobs_demo.faiss data/demo/jobs_demo.faiss.json "$SPACE_DIR/data/demo/"
cp data/processed/term_idf.json "$SPACE_DIR/data/processed/"

# The Space's own README.md (this file, front-matter included) --
# NOT the project root README.md.
cp deploy/huggingface/README.md "$SPACE_DIR/README.md"

cd "$SPACE_DIR"
git add -A
git commit -m "Deploy: <describe what changed>"
git push
```

Then watch the build at `https://huggingface.co/spaces/<hf-username>/talentrank`
— build logs are the only debugging surface for a Space, and they are slow.
Anything reproducible locally (`docker build --target runtime .`) should be
reproduced locally first, per `.claude/enhancements/15-deploy-hf-and-vercel.md`'s
own risk note.

## Secrets and variables

Set via the Space's **Settings** tab, or the CLI — never in this front-matter
(which is public) and never committed to the Space repo:

```bash
hf spaces secrets set <hf-username>/talentrank TALENTRANK_DATABASE_URL "postgresql+asyncpg://..."
hf spaces variables set <hf-username>/talentrank TALENTRANK_CORS_ALLOWED_ORIGINS "https://talentrank.vercel.app,http://localhost:5173,http://127.0.0.1:5173"
hf spaces variables set <hf-username>/talentrank TALENTRANK_CORS_ALLOW_ORIGIN_REGEX "https://talentrank-[a-z0-9-]+\.vercel\.app"
hf spaces variables set <hf-username>/talentrank TALENTRANK_AUTH_REGISTRATION_ENABLED "false"
```

- `TALENTRANK_DATABASE_URL` — a managed Postgres connection string (Neon free
  tier), **as a secret, not a variable**: Hugging Face Spaces has an
  ephemeral filesystem, so SQLite would lose every account on the next
  restart (a Space restarts on every push, rebuild, and after idle).
- `TALENTRANK_CORS_ALLOW_ORIGIN_REGEX` matters because Vercel gives every
  preview deployment its own subdomain — without the regex, every preview
  URL is CORS-blocked against this API.
- `TALENTRANK_AUTH_REGISTRATION_ENABLED=false` closes public signup after a
  demo account exists, so an open registration form on a public demo
  doesn't collect junk accounts. Toggle back to `true` (no rebuild needed,
  just a variable + restart) if open signup is wanted again.

## Rollback note

A migration applied to the managed Postgres database is **not** reverted by
redeploying a previous image — `docker-entrypoint.sh` runs `alembic upgrade
head` on every container start, forward only. See the general version of
this warning in `../../docs/OPERATIONS.md`; this doc doesn't duplicate it.

## Never

- Never commit a Hugging Face token, a database URL, or any `.env` file to
  the Space repo.
- Never put a number in this file, the UI, or a commit message that isn't
  already a row in `../../.claude/reference/measured-facts.md`.
