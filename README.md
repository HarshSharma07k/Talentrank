# TalentRank

[![CI](https://github.com/HarshSharma07k/Talentrank/actions/workflows/ci.yml/badge.svg)](https://github.com/HarshSharma07k/Talentrank/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0D9488?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-Not%20Specified-lightgrey.svg)](#engineering-decisions-and-limitations)

TalentRank matches resumes to job postings with a two-stage retrieval pipeline: a bi-encoder does fast FAISS recall over the full corpus, then a cross-encoder reranks the shortlist for precision. It's built like a small production search service rather than a notebook demo — offline index building, a cached embedding layer, a real API surface, and evaluation numbers that come from actually running the eval script, not from a table someone typed by hand.

## Live demo

- App: https://talentrank-lime.vercel.app
- API: https://talentrank-api-328510345909.us-central1.run.app/health

The hosted demo runs on a stratified ~25,000-posting subsample of the full corpus (`data/demo/`), on a free-tier host. Every number below is labeled with which corpus and which hardware produced it — hosted and local figures are never averaged together or presented as one number. The API scales to zero when idle, so the first request after a quiet stretch will be slower while it cold-starts (about 9 seconds to reload both models and the index) before settling into normal latency.

## How it's built

The design is retrieval-first: run the expensive model only over a short shortlist, not the whole corpus.

```mermaid
flowchart LR
    A[User Input\nResume Text] --> B[Bi-Encoder\nall-MiniLM-L6-v2]
    B --> C[FAISS\nTop 100]
    C --> D[Cross-Encoder Reranker\nms-marco-MiniLM-L-6-v2]
    D --> E[FastAPI Output\nRanked Jobs + Scores]
```

The corpus gets embedded once, offline, and written to disk. At request time, the resume is embedded, FAISS pulls the top 100 nearest jobs, and the cross-encoder reorders that shortlist before the API responds.

## What this is meant to demonstrate

Two-stage semantic search of the kind used by real talent-matching systems, with the offline indexing work kept separate from the online serving path so latency and maintainability don't fight each other. Retrieval quality is measured with NDCG@10 rather than assumed, serving latency is measured on real hardware rather than estimated, and the API surface is plain enough to containerize and demo without ceremony.

## Stack

Python 3.13, sentence-transformers, faiss-cpu, FastAPI and Uvicorn, Pydantic, pandas/numpy/scikit-learn, Docker, pytest.

## Measured results

Every number below was measured directly, with the exact command that produced it kept on record — nothing here was estimated or rounded up to look better. Local and hosted numbers are kept separate throughout, since they come from different hardware and (for the hosted demo) a smaller corpus.

**Corpus size** — full corpus (local): 123,849 job postings. Hosted demo corpus: 25,911 postings, a stratified sample with every job family represented.

**Evaluation, full corpus, local:**

| Pipeline stage | NDCG@10 | Notes |
| :--- | :--- | :--- |
| Bi-encoder baseline | 0.0000 | Sparse proxy labels make exact matches hard to score. |
| + cross-encoder rerank | 0.0071 | Reranking improves the shortlist under the same labeled setup. |

The shipped config (`top_k=30`, `cross_encoder_max_length=256`, `rerank_text_max_chars=1200`) pushes this to NDCG@10 = 0.0100 while cutting local `/match` latency 4.8× (666.1 ms to 138.7 ms p50). The full latency-vs-NDCG matrix, including every configuration that was tried and rejected, is in `measured-facts.md`.

**Latency:**

| Environment | p50 latency | Notes |
| :--- | :--- | :--- |
| Local, CPU (shipped config, top_k=30) | 138.7 ms | Full corpus, this dev machine. |
| Local, GPU (RTX 3050, shipped config) | 166.8 ms | Slower than CPU — a single 30-pair cross-encoder batch is too small for CUDA overhead to pay off. |
| Hosted (Cloud Run, demo corpus) | 3164.9 ms | Includes public-internet round trip to us-central1; a free 2-vCPU host is genuinely slower than local CPU, not a bug. |

That 3.2s hosted figure is the real number a visitor sees, not one chosen to look good. It's what you get from a $0/month, 2-vCPU, scale-to-zero host plus a real network hop — the 138.7ms local figure is the same code on dedicated hardware with no network in the way. Both are true measurements; neither stands in for the other.

## Prerequisites

Docker installed and running, Python 3.13.

## Regenerating data and the index

`data/processed/` (cleaned parquet files and the FAISS index) is gitignored — it's derived data, too large to commit. After cloning, regenerate it before running locally or building the Docker image:

1. Place the raw source CSVs under `data/raw/`, matching this layout:

   ```text
   data/raw/
   ├── archive/
   │   ├── linkedin_job_postings.csv
   │   └── job_summary.csv
   ├── archive (1)/
   │   └── postings.csv
   └── archive (3)/
       └── Resume/
           └── Resume.csv
   ```

2. Build the cleaned corpora and relevance pairs:

   ```bash
   python scripts/prep_data.py
   ```

3. Build the embeddings cache and FAISS index:

   ```bash
   python scripts/build_index.py
   ```

Only after step 3 do `data/processed/jobs_clean.parquet` and `data/processed/jobs.faiss` exist — both the local server and the Docker build need them.

## Setup

### Run with Docker

The API image ([`Dockerfile`](Dockerfile)) is a multi-stage build that bakes both model weights in offline (`HF_HUB_OFFLINE=1` at runtime, so nothing gets fetched from Hugging Face on container start), installs the CPU-only `torch` wheel regardless of host OS, and serves via Gunicorn plus a Uvicorn worker as a non-root user. It ships the 25k demo corpus (`data/demo/`), not the gitignored full corpus. [`docker-compose.yml`](docker-compose.yml) also builds and serves the frontend (step 4 below) behind nginx:

```bash
docker compose up --build
# API:      http://localhost:8000/health
# Frontend: http://localhost:8080
```

The in-process cache is the default. Redis is wired in but off by default — to exercise it instead:

```bash
docker compose --profile redis up --build
```

To build and run just the API image without compose:

```bash
docker build -t talentrank-api --target runtime .
docker run -p 8000:7860 talentrank-api
```

### Run locally with Python

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.talentrank.api:app --reload
```

The server auto-detects a CUDA GPU at startup (`torch.cuda.is_available()`) and falls back to CPU otherwise — `/health`'s `device` field reports which one is active. A plain `pip install -r requirements.txt` always installs the CPU-only `torch` wheel on Windows, even on a CUDA-capable machine, because the requirements file pins a version, not a build variant. To use a local GPU, reinstall `torch` from PyTorch's CUDA index afterward:

```bash
pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128 --force-reinstall
```

Measured on this project's own hardware (an RTX 3050 Laptop GPU, 4.29 GB VRAM): the GPU wasn't actually faster for `/match` — 166.8 ms p50 versus 138.7 ms p50 on CPU, at the shipped `top_k=30` config. A single request's cross-encoder pass over only 30 candidate pairs is small enough that CUDA kernel-launch and host-device transfer overhead outweighs the compute advantage. The GPU earns its keep on batch/offline work instead — `scripts/build_index.py` encoding the full corpus, for instance.

### Query the API

```bash
curl -X POST "http://localhost:8000/match" \
  -H "Content-Type: application/json" \
  -d "{\"resume_text\": \"Experienced Python backend engineer with machine learning expertise.\"}"
```

### Run the frontend

A React + TypeScript + Tailwind client lives in `frontend/`. With the API running on `http://localhost:8000`:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Then open `http://localhost:5173`. See `frontend/README.md` for details.

## Deployment

The frontend is a static Vite build on Vercel — `frontend/vercel.json` handles the SPA rewrite so client-side routes survive a page reload. The API runs as a Docker image on Google Cloud Run (2 vCPU / 2 GiB, scales to zero when idle), built from the same [`Dockerfile`](Dockerfile) used locally and pushed to Artifact Registry. The database is managed Postgres on [Neon](https://neon.tech)'s free tier, since Cloud Run's filesystem is ephemeral and SQLite would lose every account on the next cold start.

The original plan targeted a Hugging Face Docker Space, back when its `cpu-basic` tier was free. Partway through the project, Hugging Face started requiring a PRO subscription ($9/mo) for Docker and Gradio Spaces on new accounts, even on that "free" tier — confirmed live while actually trying to deploy, not assumed from documentation. Cloud Run's own perpetual free tier turned out to be the closer match to the original $0/month goal, and it runs the existing Dockerfile without any changes. `deploy/huggingface/README.md` is kept as a written runbook for the HF path in case that becomes the better option again — it just wasn't used for this deploy.

## Repository layout

```text
talentrank/
├── README.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── data/
├── scripts/
├── src/talentrank/
├── frontend/          # frontend/Dockerfile, frontend/nginx.conf
└── tests/
```

## Engineering decisions and limitations

**The sparse label problem.** The absolute NDCG scores look low because the proxy evaluation dictionary is sparse. FAISS frequently returns genuinely good semantic matches — a Data Scientist resume pulling a Data Engineer role, for example — that just don't happen to have a binary 1 in the proxy answer key, so they score as 0. The relative improvement from reranking is still real evidence the cross-encoder is doing its job; the absolute number just isn't a reliable yardstick given how the labels were built.

**Hash-map lookups instead of row scans.** Profiling found the API bottlenecked on Pandas doing O(N) row lookups inside the retrieval loop. Setting the dataframe index to `job_id` switched that to a native hash lookup and cut multiple seconds off the API latency.
