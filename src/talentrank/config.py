"""Default configuration for TalentRank."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MODELS_DIR = BASE_DIR / "models"
INDEX_DIR = BASE_DIR / "index"
EMBEDDINGS_CACHE_DIR = PROCESSED_DATA_DIR / "embeddings_cache"
JOB_INDEX_PATH = PROCESSED_DATA_DIR / "jobs.faiss"
JOBS_CLEAN_PATH = PROCESSED_DATA_DIR / "jobs_clean.parquet"

BI_ENCODER_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
CROSS_ENCODER_MODEL_NAME = "ms-marco-MiniLM-L-6-v2"
EMBEDDING_BATCH_SIZE = 64
HNSW_M = 32
HNSW_EF_CONSTRUCTION = 200
HNSW_EF_SEARCH = 64

TOP_K = 10
CANDIDATE_K = 100
