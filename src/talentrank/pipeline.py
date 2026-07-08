"""Phase 3 retrieval and reranking pipeline for TalentRank."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from src.talentrank.config import JOBS_CLEAN_PATH, JOB_INDEX_PATH
from src.talentrank.embeddings import TextEmbeddingEncoder
from src.talentrank.index import FaissIndexManager
from src.talentrank.rerank import rerank


@lru_cache(maxsize=1)
def _load_jobs_frame() -> pd.DataFrame:
    jobs_path = Path(JOBS_CLEAN_PATH)
    if not jobs_path.exists():
        raise FileNotFoundError(f"Jobs parquet file does not exist: {jobs_path}")
    
    df = pd.read_parquet(jobs_path)
    
    # OPTIMIZATION: Convert once, set as index for instant O(1) lookups
    df["job_id"] = df["job_id"].astype(str)
    df.set_index("job_id", inplace=True)
    return df

@lru_cache(maxsize=1)
def _load_index_manager() -> FaissIndexManager:
    index_path = Path(JOB_INDEX_PATH)
    if not index_path.exists():
        raise FileNotFoundError(f"FAISS index file does not exist: {index_path}")
    return FaissIndexManager.load_index(index_path)

def _resolve_job_row(jobs: pd.DataFrame, job_id: int) -> dict[str, Any] | None:
    str_id = str(job_id)
    
    # Instant hash-map lookup
    if str_id not in jobs.index:
        return None

    row = jobs.loc[str_id].to_dict()
    row["job_id"] = int(job_id)
    return row

def retrieve_only(resume_text: str, top_k: int) -> list[dict[str, Any]]:
    """Retrieve the top_k jobs with bi-encoder scores only."""

    if top_k <= 0:
        return []

    query_text = " ".join(str(resume_text).split())
    if not query_text:
        return []

    encoder = TextEmbeddingEncoder()
    query_embedding = encoder.encode_texts([query_text], show_progress_bar=False)[0]

    index_manager = _load_index_manager()
    hits = index_manager.search(query_embedding, k=top_k)
    jobs = _load_jobs_frame()

    candidates: list[dict[str, Any]] = []
    for hit in hits:
        job_row = _resolve_job_row(jobs, hit.job_id)
        if job_row is None:
            continue

        job_row["job_text"] = job_row.get("text", "")
        job_row["bi_encoder_score"] = float(hit.score)
        candidates.append(job_row)

    return candidates

def match(resume_text: str, top_k: int = 100, top_n: int = 10) -> list[dict[str, Any]]:
    """Retrieve candidates and rerank them with the cross-encoder."""

    candidates = retrieve_only(resume_text=resume_text, top_k=top_k)
    return rerank(query=resume_text, candidates=candidates, top_n=top_n)