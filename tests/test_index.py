"""Regression tests for finding 4: `ef_search` was read from the sidecar into
`self.ef_search` on load but never pushed onto the live FAISS index object, so
tuning it did nothing, and a `k` above the built `ef_search` degraded results.
See .claude/enhancements/00-overview.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from src.talentrank.index import FaissIndexManager


def test_build_save_load_roundtrip(tiny_index: FaissIndexManager, tmp_path: Path) -> None:
    index_path = tiny_index.save_index(tmp_path / "tiny.faiss")

    loaded = FaissIndexManager.load_index(index_path)

    assert loaded.dimension == tiny_index.dimension
    assert loaded.index.ntotal == tiny_index.index.ntotal


def test_search_returns_k_hits_with_correct_ids(tiny_index: FaissIndexManager) -> None:
    query = np.random.default_rng(1).normal(size=384).astype(np.float32)
    query /= np.linalg.norm(query)

    hits = tiny_index.search(query, k=5)

    assert len(hits) == 5
    assert {hit.job_id for hit in hits} <= set(range(1, 21))


def test_ef_search_applied_after_load(tiny_index: FaissIndexManager, tmp_path: Path) -> None:
    index_path = tiny_index.save_index(tmp_path / "tiny.faiss")
    metadata_path = index_path.with_suffix(index_path.suffix + ".json")
    metadata = json.loads(metadata_path.read_text())
    metadata["ef_search"] = 17
    metadata_path.write_text(json.dumps(metadata))

    loaded = FaissIndexManager.load_index(index_path)

    assert loaded.ef_search == 17
    assert loaded._hnsw_index().hnsw.efSearch == 17


def test_ef_search_clamped_to_k(tiny_index: FaissIndexManager) -> None:
    tiny_index.ef_search = 5
    tiny_index._apply_ef_search()
    query = np.random.default_rng(2).normal(size=384).astype(np.float32)
    query /= np.linalg.norm(query)

    tiny_index.search(query, k=20)

    assert tiny_index.ef_search >= 20
    assert tiny_index._hnsw_index().hnsw.efSearch >= 20
