"""Configuration for TalentRank.

`Settings` is the live, env-driven source of truth — new code must call
`get_settings()`. The module-level constants below it (`BASE_DIR`,
`JOB_INDEX_PATH`, etc.) are a back-compat snapshot taken at import time, kept
so every existing `from src.talentrank.config import X` import keeps working
unchanged. Because they snapshot at import, they will not reflect an env var
set *after* this module was first imported — that is expected, not a bug.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Env-driven configuration, prefixed `TALENTRANK_`."""

    model_config = SettingsConfigDict(
        env_prefix="TALENTRANK_",
        env_file=".env",
        extra="ignore",
        protected_namespaces=(),
    )

    base_dir: Path = Path(__file__).resolve().parents[2]
    corpus_profile: Literal["full", "demo"] = "full"

    # Derived paths. Defaults must be `None` here -- pydantic evaluates field
    # defaults independently, so `data_dir: Path = base_dir / "data"` cannot see the
    # resolved value of a sibling field. Filled in by `_derive_paths` below instead.
    data_dir: Path | None = None
    raw_data_dir: Path | None = None
    processed_data_dir: Path | None = None
    embeddings_cache_dir: Path | None = None
    jobs_clean_path: Path | None = None
    job_index_path: Path | None = None
    term_idf_path: Path | None = None

    # Models.
    bi_encoder_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    cross_encoder_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    embedding_batch_size: int = 64

    # FAISS HNSW.
    hnsw_m: int = 32
    hnsw_ef_construction: int = 200
    hnsw_ef_search: int = 64

    # Retrieval / rerank sizing.
    # 30, not the 100 this project started with, and not the 25 enhancements/08
    # itself first suggested: measured NDCG@10 at top_k=25 dropped to 0.0000 (versus
    # 0.0071 at top_k=100), while top_k=30 held at 0.0077 -- so 30 was chosen because
    # it is the smallest value this project measured with zero NDCG regression, not
    # because it is a round number. See measured-facts.md for the full matrix.
    default_top_k: int = 30
    default_top_n: int = 10
    max_top_k: int = 200
    max_top_n: int = 50
    min_resume_chars: int = 40
    max_resume_chars: int = 20000
    cross_encoder_max_length: int = 256
    cross_encoder_quantize: bool = False
    rerank_text_max_chars: int = 1200

    # Concurrency.
    torch_num_threads: int = 2
    max_concurrent_inferences: int = 1
    inference_queue_timeout_seconds: float = 20.0
    max_request_threads: int = 8  # Starlette's default threadpool is 40; too much contention on 2 vCPU

    # Cache.
    cache_backend: Literal["memory", "redis"] = "memory"
    cache_ttl_seconds: int = 3600
    cache_max_entries: int = 256
    redis_url: str | None = None

    # Rate limiting.
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60

    # Upload / explainability / filters.
    max_upload_bytes: int = 5_000_000
    description_max_chars: int = 1200
    explain_max_terms: int = 12
    explain_min_idf: float = 1.0  # floor for a shared term to be highlightable
    filter_overfetch_factor: int = 3

    # Demo corpus.
    demo_corpus_size: int = 25000

    # CORS / serving.
    # `NoDecode`: pydantic-settings otherwise tries to JSON-decode a `list[str]` env
    # value before validators run, so `TALENTRANK_CORS_ALLOWED_ORIGINS=a,b` would fail
    # to parse rather than reach `_parse_cors_origins` below.
    cors_allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    cors_allow_origin_regex: str | None = None
    api_port: int = 8000

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string from the env, in addition to a list."""

        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _derive_paths(self) -> "Settings":
        if self.data_dir is None:
            self.data_dir = self.base_dir / "data"
        if self.raw_data_dir is None:
            self.raw_data_dir = self.data_dir / "raw"
        if self.processed_data_dir is None:
            self.processed_data_dir = self.data_dir / "processed"
        if self.embeddings_cache_dir is None:
            self.embeddings_cache_dir = self.processed_data_dir / "embeddings_cache"
        if self.term_idf_path is None:
            self.term_idf_path = self.processed_data_dir / "term_idf.json"

        if self.corpus_profile == "demo":
            demo_dir = self.data_dir / "demo"
            if self.jobs_clean_path is None:
                self.jobs_clean_path = demo_dir / "jobs_demo.parquet"
            if self.job_index_path is None:
                self.job_index_path = demo_dir / "jobs_demo.faiss"
        else:
            if self.jobs_clean_path is None:
                self.jobs_clean_path = self.processed_data_dir / "jobs_clean.parquet"
            if self.job_index_path is None:
                self.job_index_path = self.processed_data_dir / "jobs.faiss"

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide `Settings` singleton. Call `.cache_clear()` in tests
    after changing env vars."""

    return Settings()


# --- Back-compat constants -------------------------------------------------
# Snapshot of `get_settings()` at import time. Every name here previously lived
# in this module as a hardcoded constant; do not delete this block -- index.py,
# embeddings.py, data.py, pipeline.py, rerank.py, api.py and several scripts
# import directly from it.
settings = get_settings()

BASE_DIR = settings.base_dir
DATA_DIR = settings.data_dir
RAW_DATA_DIR = settings.raw_data_dir
PROCESSED_DATA_DIR = settings.processed_data_dir
EMBEDDINGS_CACHE_DIR = settings.embeddings_cache_dir
JOB_INDEX_PATH = settings.job_index_path
JOBS_CLEAN_PATH = settings.jobs_clean_path

BI_ENCODER_MODEL_NAME = settings.bi_encoder_model_name
CROSS_ENCODER_MODEL_NAME = settings.cross_encoder_model_name
EMBEDDING_BATCH_SIZE = settings.embedding_batch_size

HNSW_M = settings.hnsw_m
HNSW_EF_CONSTRUCTION = settings.hnsw_ef_construction
HNSW_EF_SEARCH = settings.hnsw_ef_search

DEFAULT_TOP_K = settings.default_top_k
DEFAULT_TOP_N = settings.default_top_n

CORS_ALLOWED_ORIGINS = settings.cors_allowed_origins
