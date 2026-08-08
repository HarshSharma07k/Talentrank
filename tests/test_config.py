"""Tests for the pydantic-settings configuration. See .claude/enhancements/01."""

from __future__ import annotations

import pytest

from src.talentrank import config
from src.talentrank.config import get_settings


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TALENTRANK_DEFAULT_TOP_K", "25")
    get_settings.cache_clear()

    assert get_settings().default_top_k == 25


def test_legacy_constants_importable() -> None:
    settings = get_settings()

    assert config.BASE_DIR == settings.base_dir
    assert config.DATA_DIR == settings.data_dir
    assert config.RAW_DATA_DIR == settings.raw_data_dir
    assert config.PROCESSED_DATA_DIR == settings.processed_data_dir
    assert config.EMBEDDINGS_CACHE_DIR == settings.embeddings_cache_dir
    assert config.JOB_INDEX_PATH == settings.job_index_path
    assert config.JOBS_CLEAN_PATH == settings.jobs_clean_path
    assert config.BI_ENCODER_MODEL_NAME == settings.bi_encoder_model_name
    assert config.CROSS_ENCODER_MODEL_NAME == settings.cross_encoder_model_name
    assert config.EMBEDDING_BATCH_SIZE == settings.embedding_batch_size
    assert config.HNSW_M == settings.hnsw_m
    assert config.HNSW_EF_CONSTRUCTION == settings.hnsw_ef_construction
    assert config.HNSW_EF_SEARCH == settings.hnsw_ef_search
    assert config.DEFAULT_TOP_K == settings.default_top_k
    assert config.DEFAULT_TOP_N == settings.default_top_n
    assert config.CORS_ALLOWED_ORIGINS == settings.cors_allowed_origins


def test_corpus_profile_switches_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TALENTRANK_CORPUS_PROFILE", "demo")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.jobs_clean_path is not None
    assert settings.job_index_path is not None
    assert "demo" in settings.jobs_clean_path.parts
    assert "demo" in settings.job_index_path.parts
    assert settings.jobs_clean_path.name == "jobs_demo.parquet"
    assert settings.job_index_path.name == "jobs_demo.faiss"


def test_cors_origins_parse_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TALENTRANK_CORS_ALLOWED_ORIGINS", "https://a.example.com,https://b.example.com")
    get_settings.cache_clear()

    assert get_settings().cors_allowed_origins == ["https://a.example.com", "https://b.example.com"]
