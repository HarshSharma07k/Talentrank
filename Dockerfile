# syntax=docker/dockerfile:1
#
# Four stages -- see .claude/enhancements/14-containerization.md:
#   builder      -- installs deps into a venv (CPU-only torch, not the CUDA wheel
#                    this repo's own dev machine uses -- see requirements.txt).
#   models       -- bakes both model weights into an HF cache directory, offline
#                    at runtime (HF_HUB_OFFLINE=1 in runtime-base *proves* it).
#   runtime-base -- the non-root, healthchecked image with code but no data. This
#                    is the target CI builds (`--target runtime-base`) so a docker
#                    build never needs the gitignored data/ directories.
#   runtime      -- runtime-base plus the demo corpus, ready to serve.
ARG PYTHON_VERSION=3.13
ARG APP_PORT=7860

FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.txt ./
# --extra-index-url ...whl/cpu is not optional: this project's requirements.txt
# pins torch's *version* only, and on Linux that version resolves to the CUDA
# wheel by default -- multi-gigabyte, and the most common way this deployment
# fails to fit a free CPU-tier host. See engineering-challenges.md.
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

FROM builder AS models

ENV HF_HOME=/opt/hf-cache
WORKDIR /app
COPY scripts/fetch_models.py ./scripts/fetch_models.py
COPY src/ ./src/
RUN python scripts/fetch_models.py

FROM python:${PYTHON_VERSION}-slim AS runtime-base

ARG APP_PORT
COPY --from=builder /opt/venv /opt/venv
COPY --from=models /opt/hf-cache /opt/hf-cache
ENV PATH="/opt/venv/bin:${PATH}" \
    HF_HOME=/opt/hf-cache \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    APP_PORT=${APP_PORT}

WORKDIR /app
COPY src/ ./src/
# enhancements/24: needed for the entrypoint's `alembic upgrade head` step.
# alembic.ini's own sqlalchemy.url is deliberately blank -- migrations/env.py reads
# the real URL from get_settings(), the one source of truth (Rule 4).
COPY migrations/ ./migrations/
COPY alembic.ini ./alembic.ini
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

# uid 1000 is both good practice and a Hugging Face Spaces requirement. This is
# also why enhancements/07 moved the embeddings-cache mkdir off the request path
# -- it would fail against this read-mostly, non-root filesystem. `mkdir -p data`
# here, before the chown, matters for enhancements/24: without a database service
# configured, Settings._derive_paths falls back to a SQLite file under
# {base_dir}/data/, and Docker COPY (in the runtime stage below) creates any
# directory it needs as root regardless of this stage's ownership -- appuser could
# not otherwise write a fresh talentrank.db here.
RUN mkdir -p /app/data && useradd -m -u 1000 appuser && chown -R appuser:appuser /app /opt/hf-cache
USER appuser

EXPOSE ${APP_PORT}
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['APP_PORT'] + '/health')" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]

FROM runtime-base AS runtime

# Only the demo corpus, not data/processed/ -- that's the bug this rewrite fixes.
# term_idf.json is the one exception: config.py's Settings._derive_paths keeps
# term_idf_path on data/processed/ regardless of corpus_profile (the IDF map is
# built from the full corpus and is correct to reuse under the demo subsample
# too), so explainability needs this one small file even though the demo corpus
# itself lives under data/demo/. --chown keeps these appuser-owned like everything
# else under /app -- COPY otherwise creates new paths as root regardless of the
# USER already set in runtime-base.
COPY --chown=appuser:appuser data/demo/ ./data/demo/
COPY --chown=appuser:appuser data/processed/term_idf.json ./data/processed/term_idf.json
ENV TALENTRANK_CORPUS_PROFILE=demo

# One worker: two would double the model's resident memory *and* halve the cores
# each gets on a 2-vCPU box, and the model forward pass is the bottleneck, not
# the request loop. WEB_CONCURRENCY stays overridable for anyone who measures
# otherwise on different hardware.
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-1} -b 0.0.0.0:${APP_PORT} --timeout 120 src.talentrank.api:app"]
