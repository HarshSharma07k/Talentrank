"""Offline Phase 2 index builder for TalentRank."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.talentrank.config import EMBEDDINGS_CACHE_DIR, JOB_INDEX_PATH, EMBEDDING_BATCH_SIZE, PROCESSED_DATA_DIR  # noqa: E402
from src.talentrank.embeddings import TextEmbeddingEncoder  # noqa: E402
from src.talentrank.index import FaissIndexManager, save_index  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for offline index building."""

    parser = argparse.ArgumentParser(description="Build the TalentRank FAISS index from cleaned jobs.")
    parser.add_argument(
        "--jobs-path",
        type=Path,
        default=PROCESSED_DATA_DIR / "jobs_clean.parquet",
        help="Path to the cleaned jobs parquet file.",
    )
    parser.add_argument(
        "--index-path",
        type=Path,
        default=JOB_INDEX_PATH,
        help="Path where the FAISS index will be written.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=EMBEDDINGS_CACHE_DIR,
        help="Directory used for embedding cache files.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=EMBEDDING_BATCH_SIZE,
        help="Batch size used for SentenceTransformer encoding.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Re-encode job texts instead of reusing the on-disk cache.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the encoding progress bar.",
    )
    return parser.parse_args()


def build_index(jobs_path: Path, index_path: Path, cache_dir: Path, batch_size: int, use_cache: bool, show_progress: bool) -> Path:
    """Build and persist the job posting FAISS index."""

    jobs = pd.read_parquet(jobs_path)
    required_columns = {"job_id", "job_title", "text"}
    missing_columns = required_columns.difference(jobs.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns in {jobs_path}: {sorted(missing_columns)}")

    combined_texts = (
        jobs["job_title"].fillna("").astype(str).str.strip()
        + " "
        + jobs["text"].fillna("").astype(str).str.strip()
    ).str.replace(r"\s+", " ", regex=True).str.strip().tolist()

    encoder = TextEmbeddingEncoder(cache_dir=cache_dir)
    embeddings = encoder.encode_texts(
        texts=combined_texts,
        batch_size=batch_size,
        use_cache=use_cache,
        show_progress_bar=show_progress,
    )

    job_ids = jobs["job_id"].astype("int64").tolist()
    index_manager = FaissIndexManager(dimension=embeddings.shape[1])
    index_manager.add(embeddings, job_ids)
    return save_index(index_manager, index_path)


def main() -> None:
    """Entry point for offline FAISS index construction."""

    args = parse_args()
    index_file = build_index(
        jobs_path=args.jobs_path,
        index_path=args.index_path,
        cache_dir=args.cache_dir,
        batch_size=args.batch_size,
        use_cache=not args.no_cache,
        show_progress=not args.no_progress,
    )
    print(f"Saved FAISS index to {index_file}")


if __name__ == "__main__":
    main()