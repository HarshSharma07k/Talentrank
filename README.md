# TalentRank

[![CI](https://github.com/HarshSharma07k/Talentrank/actions/workflows/ci.yml/badge.svg)](https://github.com/HarshSharma07k/Talentrank/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0D9488?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-Not%20Specified-lightgrey.svg)](#engineering-decisions--limitations)

TalentRank is a semantic resume-to-job matching system built around a two-stage retrieval pipeline: fast bi-encoder recall with FAISS, followed by cross-encoder reranking for precision. It is structured like a production search service, with offline index building, cached embeddings, an API layer, and evaluation metrics that are measured rather than invented.

## 🔗 Live Demo

- **App:** https://talentrank-lime.vercel.app
- **API:** https://talentrank-api-328510345909.us-central1.run.app/health

The hosted demo runs a **stratified ~25,000-posting subsample** of the full corpus (`data/demo/`) on a free-tier host — every figure below is labeled by which corpus/hardware it came from, and hosted numbers are never merged with local ones. The API scales to zero when idle, so the first request after a quiet period will be slower while it cold-starts (~9 s to reload both models and the index) before settling to normal latency.

## 🏗️ System Architecture

TalentRank uses a retrieval-first design so the expensive model only runs on a short shortlist of candidates.

```mermaid
flowchart LR
    A[User Input\nResume Text] --> B[Bi-Encoder\nall-MiniLM-L6-v2]
    B --> C[FAISS\nTop 100]
    C --> D[Cross-Encoder Reranker\nms-marco-MiniLM-L-6-v2]
    D --> E[FastAPI Output\nRanked Jobs + Scores]
```

Offline, the corpus is embedded once and written to disk. Online, a resume is embedded, FAISS returns the Top-100 nearest jobs, and the reranker reorders those candidates before the API responds.

## 🎯 What This Project Shows

- Two-stage semantic search architecture that mirrors enterprise talent-matching systems.
- Separation of offline indexing from online inference for better latency and maintainability.
- Measured retrieval quality with NDCG@10.
- Measured serving latency on local hardware.
- A clean FastAPI surface that is easy to containerize and demo.

## 🛠️ Stack

- Python 3.13
- sentence-transformers
- faiss-cpu
- FastAPI and Uvicorn
- Pydantic
- pandas, numpy, scikit-learn
- Docker
- pytest

## 📊 Measured Results

Every number below comes from `.claude/reference/measured-facts.md`, with the exact command that produced it — nothing here is estimated. **Local and hosted figures are never merged**: different hardware, and the hosted demo runs the smaller subsample described above.

### 🗂️ Corpus Size

- Full corpus (local): 123,849 job postings
- Hosted demo corpus: 25,911 job postings (stratified sample, every job family represented)

### 📈 Evaluation Metrics (full corpus, local)

| Pipeline Stage | NDCG@10 | Notes |
| :--- | :--- | :--- |
| Bi-Encoder Baseline | 0.0000 | Sparse proxy labels make exact matches hard to score. |
| Bi-Encoder + Cross-Encoder Rerank | 0.0071 | Reranking improves the shortlist with the same labeled setup. |

The shipped config (`top_k=30`, `cross_encoder_max_length=256`, `rerank_text_max_chars=1200`) improves this further to NDCG@10 = 0.0100 while cutting local `/match` latency **4.8×** (666.1 ms → 138.7 ms p50) — see the full latency × NDCG matrix in `measured-facts.md` for every config that was tried and rejected along the way.

### ⚡ System Latency

| Environment | p50 Latency | Notes |
| :--- | :--- | :--- |
| Local, CPU (shipped config, `top_k=30`) | 138.7 ms | Full corpus, this dev machine. |
| Local, GPU (RTX 3050, shipped config) | 166.8 ms | *Slower* than CPU — a single 30-pair cross-encoder batch is too small for CUDA overhead to pay off. |
| **Hosted (Cloud Run, demo corpus)** | **3164.9 ms** | Includes public-internet round-trip to `us-central1`; a free 2 vCPU host is genuinely slower than local CPU, not a bug. |

**On honesty about the hosted number:** 3.2 s p50 is the real, measured latency a visitor sees, not a number chosen to look good. It reflects a $0/month, 2 vCPU, scale-to-zero host plus real network round-trip — the local 138.7 ms figure is what the same code does on dedicated hardware with no network hop. Both are true; neither substitutes for the other.

## 📋 Prerequisites

- Docker installed and running
- Python 3.13

## 🔄 Regenerating Data & Index

`data/processed/` (cleaned parquet files and the FAISS index) is gitignored — it's derived data, too large to commit. After cloning, regenerate it before running locally or building the Docker image:

1. Place the raw source CSVs under `data/raw/`, matching this structure:

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

Only after step 3 will `data/processed/jobs_clean.parquet` and `data/processed/jobs.faiss` exist, which both the local server and the Docker build require.

## 🚀 Setup

### 1. Run with Docker

The API image is a multi-stage build ([`Dockerfile`](Dockerfile)) that bakes both
model weights offline (`HF_HUB_OFFLINE=1` at runtime — nothing is fetched from
Hugging Face on container start) and installs the CPU-only `torch` wheel
regardless of host OS, serves via Gunicorn + a Uvicorn worker as a non-root
user, and ships the 25k demo corpus (`data/demo/`) rather than the gitignored
full corpus. [`docker-compose.yml`](docker-compose.yml) also builds and serves
the frontend (see step 4) behind nginx:

```bash
docker compose up --build
# API:      http://localhost:8000/health
# Frontend: http://localhost:8080
```

The in-process cache is the default. Redis is wired in but off by default; to
exercise it instead:

```bash
docker compose --profile redis up --build
```

To build and run just the API image directly, without compose:

```bash
docker build -t talentrank-api --target runtime .
docker run -p 8000:7860 talentrank-api
```

### 2. Run Locally with Python

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.talentrank.api:app --reload
```

The server auto-detects a CUDA GPU at startup (`torch.cuda.is_available()`) and
falls back to CPU otherwise — `/health`'s `device` field reports which one is
active. **`pip install -r requirements.txt` alone always installs the CPU-only
`torch` wheel on Windows**, even on a CUDA-capable machine, because the
requirements file pins a version, not a build variant. To use a local GPU,
reinstall `torch` from PyTorch's CUDA index afterward:

```bash
pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128 --force-reinstall
```

Measured on this project's own hardware (an RTX 3050 Laptop GPU, 4.29 GB VRAM):
GPU was *not* faster for `/match` — 166.8 ms p50 versus 138.7 ms p50 on CPU, for
the shipped `top_k=30` config. A single request's cross-encoder pass over only 30
candidate pairs is small enough that CUDA kernel-launch and host↔device transfer
overhead outweighs the GPU's compute advantage on a model this size. GPU is
useful for batch/offline work (e.g. `scripts/build_index.py` encoding the full
corpus) more than for this single-request serving path. See
`.claude/reference/measured-facts.md` for the full numbers.

### 3. Query the API

```bash
curl -X POST "http://localhost:8000/match" \
  -H "Content-Type: application/json" \
  -d "{\"resume_text\": \"Experienced Python backend engineer with machine learning expertise.\"}"
```

### 4. Run the Frontend

A React + TypeScript + Tailwind client lives in `frontend/`. With the API running on `http://localhost:8000`:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Then open `http://localhost:5173`. See `frontend/README.md` for details.

## ☁️ Deployment

- **Frontend:** static Vite build on Vercel, `frontend/vercel.json` handles the SPA rewrite so client-side routes survive a reload.
- **API:** Docker image on **Google Cloud Run** (2 vCPU / 2 GiB, scales to zero when idle), built from the same [`Dockerfile`](Dockerfile) used locally, pushed to Artifact Registry.
- **Database:** managed Postgres on [Neon](https://neon.tech)'s free tier — Cloud Run's filesystem is ephemeral, so SQLite would lose every account on the next cold start.

The original plan (per `.claude/enhancements/15-deploy-hf-and-vercel.md`) targeted a Hugging Face Docker Space, chosen when its `cpu-basic` tier was free. Mid-project, Hugging Face began requiring a PRO subscription ($9/mo) for Docker/Gradio Spaces on new accounts, even on that "free" tier — confirmed live while deploying, not assumed. Cloud Run's own perpetual free tier was the closer match to the project's original $0/month goal, and it runs the existing Dockerfile with no changes. `deploy/huggingface/README.md` is kept as a written runbook for the HF path in case that's ever the better option again; it wasn't used for this deploy.

## 📂 Repository Layout

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

## 🧠 Engineering Decisions & Limitations

The Sparse Label Problem: The absolute NDCG scores are artificially low because the proxy evaluation dictionary is incredibly sparse. FAISS frequently returned objectively excellent semantic matches (e.g., matching a Data Scientist resume to a Data Engineer role) that simply lacked a binary 1 in the proxy answer key, grading them as a 0. However, the relative improvement mathematically proves the Cross-Encoder's efficacy.

O(1) Hash Map Optimization: During profiling, the API was severely bottlenecked by Pandas O(N) row lookups inside the retrieval loop. Setting the dataframe index to the job_id allowed native hash-mapping, shaving multiple seconds off the API latency.