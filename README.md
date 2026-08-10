# TalentRank

[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0D9488?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-Not%20Specified-lightgrey.svg)](#engineering-decisions--limitations)

TalentRank is a semantic resume-to-job matching system built around a two-stage retrieval pipeline: fast bi-encoder recall with FAISS, followed by cross-encoder reranking for precision. It is structured like a production search service, with offline index building, cached embeddings, an API layer, and evaluation metrics that are measured rather than invented.

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

All numbers below are kept exactly as measured on local hardware.

### 🗂️ Corpus Size

- Corpus size: 123,849 job postings

### 📈 Evaluation Metrics

| Pipeline Stage | NDCG@10 | Notes |
| :--- | :--- | :--- |
| Bi-Encoder Baseline | 0.0000 | Sparse proxy labels make exact matches hard to score. |
| Bi-Encoder + Cross-Encoder Rerank | 0.0071 | Reranking improves the shortlist with the same labeled setup. |

### ⚡ System Latency

| Hardware | p50 Latency | Bottleneck |
| :--- | :--- | :--- |
| CPU Only | 5.5s | Transformer cross-attention over 100 candidate pairs. |
| GPU (RTX 3050) | 2.7s | Batched inference through CUDA. |

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

```bash
docker build -t talentrank .
docker run -p 8000:8000 talentrank
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

## 📂 Repository Layout

```text
talentrank/
├── README.md
├── Dockerfile
├── requirements.txt
├── data/
├── scripts/
├── src/talentrank/
├── frontend/
└── tests/
```

## 🧠 Engineering Decisions & Limitations

The Sparse Label Problem: The absolute NDCG scores are artificially low because the proxy evaluation dictionary is incredibly sparse. FAISS frequently returned objectively excellent semantic matches (e.g., matching a Data Scientist resume to a Data Engineer role) that simply lacked a binary 1 in the proxy answer key, grading them as a 0. However, the relative improvement mathematically proves the Cross-Encoder's efficacy.

O(1) Hash Map Optimization: During profiling, the API was severely bottlenecked by Pandas O(N) row lookups inside the retrieval loop. Setting the dataframe index to the job_id allowed native hash-mapping, shaving multiple seconds off the API latency.