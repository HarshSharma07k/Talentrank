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

from pydantic import SecretStr, field_validator, model_validator
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

    # Persistence (enhancements/19). `database_url` is `SecretStr` because in
    # production it carries a PostgreSQL password -- that is not decoration, it is
    # what stops an accidental `repr(settings)` in a log line or traceback from
    # printing a credential. Left `None` here and derived in `_derive_paths` below,
    # same pattern as the path fields above.
    database_url: SecretStr | None = None
    database_echo: bool = False  # SQL logging; never enable in production, it logs parameter values.
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_recycle_seconds: int = 1800

    # Authentication (enhancements/20).
    session_token_bytes: int = 32
    session_ttl_seconds: int = 1_209_600  # 14 days
    # Only renew expiry when the session is older than this, so the common
    # authenticated request is a pure read against the sessions table.
    session_sliding_renewal_seconds: int = 86_400
    session_max_per_user: int = 10  # bounds unlimited session-row accumulation
    # enhancements/24: bounds a single purge_expired_sessions() DELETE batch so a
    # large backlog doesn't hold one long transaction against the sessions table.
    session_purge_batch_size: int = 1000
    # OWASP's second recommended Argon2id profile, cited as a published
    # recommendation, not a value measured by this project. Deliberately not the
    # library defaults (m=65536 KiB): this service runs on 2 vCPU with
    # max_request_threads=8, so eight concurrent logins at 64 MiB each would be
    # 512 MiB of transient allocation on a box that also holds two ML models.
    argon2_time_cost: int = 2
    argon2_memory_cost_kib: int = 19_456
    argon2_parallelism: int = 1
    password_min_chars: int = 12
    password_max_chars: int = 128  # a DoS control, not a usability one -- see auth/schemas.py
    auth_rate_limit_requests: int = 5
    auth_rate_limit_window_seconds: int = 300
    authenticated_rate_limit_requests: int = 120
    # Lets the hosted demo stay open for matching but closed for signup without a
    # code change.
    auth_registration_enabled: bool = True

    # User-scoped data (enhancements/21).
    max_history_entries_per_user: int = 200  # breach: drop oldest, silently -- history is a convenience
    max_saved_lists_per_user: int = 50  # breach: 409 -- the user named this thing, do not delete it
    max_items_per_saved_list: int = 200  # breach: 409
    # Mirrors frontend/src/lib/history.ts's DESCRIPTION_STORAGE_MAX_CHARS, so a run
    # looks the same whether it came from local or server storage.
    history_description_max_chars: int = 400
    history_page_size: int = 20
    # Not in enhancements/21's own "Config keys added" list, added here per Rule 4
    # (no magic numbers): mirrors frontend/src/lib/history.ts's LABEL_MAX_CHARS,
    # used when persist_run auto-derives a label from resume_text.
    history_label_max_chars: int = 50

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
        if self.database_url is None:
            # `.as_posix()`, not the bare Path/f-string: on Windows a plain str(Path)
            # renders backslashes, which are not valid path separators inside a URL.
            self.database_url = SecretStr(f"sqlite+aiosqlite:///{(self.data_dir / 'talentrank.db').as_posix()}")

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
