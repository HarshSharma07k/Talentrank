"""FAISS index management for TalentRank Phase 2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Sequence

import faiss
import numpy as np

from src.talentrank.config import HNSW_EF_CONSTRUCTION, HNSW_EF_SEARCH, HNSW_M


@dataclass(slots=True)
class SearchHit:
    """Single nearest-neighbor search result."""

    job_id: int
    score: float


@dataclass(slots=True)
class IndexMetadata:
    """Persisted metadata for a FAISS index bundle."""

    dimension: int
    metric: int
    hnsw_m: int
    ef_construction: int
    ef_search: int
    index_kind: str


class FaissIndexManager:
    """Build, persist, load, and query a FAISS HNSW index."""

    def __init__(
        self,
        dimension: int,
        m: int = HNSW_M,
        metric: int = faiss.METRIC_INNER_PRODUCT,
        ef_construction: int = HNSW_EF_CONSTRUCTION,
        ef_search: int = HNSW_EF_SEARCH,
        index: faiss.Index | None = None,
    ) -> None:
        self.dimension = int(dimension)
        self.m = int(m)
        self.metric = int(metric)
        self.ef_construction = int(ef_construction)
        self.ef_search = int(ef_search)

        if index is None:
            base_index = faiss.IndexHNSWFlat(self.dimension, self.m, self.metric)
            base_index.hnsw.efConstruction = self.ef_construction
            self.index = faiss.IndexIDMap2(base_index)
        else:
            self.index = index

        self._apply_ef_search()

    def _hnsw_index(self) -> faiss.Index:
        """Return the HNSW-carrying index, unwrapping an IndexIDMap2 if present.

        `IndexIDMap2.index` is typed as the generic SWIG `Index` base class, which has
        no `.hnsw` attribute even when the underlying object is an `IndexHNSWFlat` --
        `downcast_index` recovers the concrete type.
        """

        if isinstance(self.index, faiss.IndexIDMap2):
            return faiss.downcast_index(self.index.index)
        return self.index

    def _apply_ef_search(self) -> None:
        """Push `self.ef_search` onto the live FAISS index object.

        Both index construction and `load_index` route through this: FAISS only reads
        `efSearch` from the HNSW struct at query time, so a value read from a metadata
        sidecar (or passed to `__init__`) does nothing until it lands here.
        """

        self._hnsw_index().hnsw.efSearch = self.ef_search

    @staticmethod
    def _as_float32_matrix(vectors: np.ndarray | Sequence[Sequence[float]]) -> np.ndarray:
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        if matrix.ndim != 2:
            raise ValueError("Expected a 1D or 2D embedding array.")
        return np.ascontiguousarray(matrix, dtype=np.float32)

    @staticmethod
    def _as_int64_ids(job_ids: Sequence[int]) -> np.ndarray:
        ids = np.asarray(job_ids, dtype=np.int64)
        if ids.ndim != 1:
            raise ValueError("Expected a flat sequence of job IDs.")
        return np.ascontiguousarray(ids, dtype=np.int64)

    def add(self, embeddings: np.ndarray | Sequence[Sequence[float]], job_ids: Sequence[int]) -> None:
        """Add job embeddings to the FAISS index with explicit job IDs."""

        vectors = self._as_float32_matrix(embeddings)
        ids = self._as_int64_ids(job_ids)
        if vectors.shape[0] != ids.shape[0]:
            raise ValueError("Embeddings and job IDs must have the same number of rows.")
        if vectors.shape[1] != self.dimension:
            raise ValueError(f"Embedding dimension mismatch: expected {self.dimension}, received {vectors.shape[1]}.")

        self.index.add_with_ids(vectors, ids)

    def search(self, query_embedding: np.ndarray | Sequence[float], k: int) -> list[SearchHit]:
        """Search the index and return the closest job IDs and similarity scores."""

        query = self._as_float32_matrix(query_embedding)
        if query.shape[1] != self.dimension:
            raise ValueError(f"Query dimension mismatch: expected {self.dimension}, received {query.shape[1]}.")

        k = int(k)
        if k > self.ef_search:
            self.ef_search = k
            self._apply_ef_search()

        scores, ids = self.index.search(query, k)
        hits: list[SearchHit] = []
        for job_id, score in zip(ids[0], scores[0]):
            if int(job_id) == -1:
                continue
            hits.append(SearchHit(job_id=int(job_id), score=float(score)))
        return hits

    def metadata(self) -> IndexMetadata:
        """Return the index metadata used for persistence."""

        return IndexMetadata(
            dimension=self.dimension,
            metric=self.metric,
            hnsw_m=self.m,
            ef_construction=self.ef_construction,
            ef_search=self.ef_search,
            index_kind=self.index.__class__.__name__,
        )

    def save_index(self, path: Path | str) -> Path:
        """Persist the FAISS index and a small metadata sidecar."""

        index_path = Path(path)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(index_path))

        metadata_path = index_path.with_suffix(index_path.suffix + ".json")
        with metadata_path.open("w", encoding="utf-8") as handle:
            json.dump(asdict(self.metadata()), handle, indent=2, sort_keys=True)

        return index_path

    @classmethod
    def load_index(cls, path: Path | str) -> "FaissIndexManager":
        """Load a persisted FAISS index and restore its manager."""

        index_path = Path(path)
        index = faiss.read_index(str(index_path))
        metadata_path = index_path.with_suffix(index_path.suffix + ".json")
        metadata = {}
        if metadata_path.exists():
            with metadata_path.open("r", encoding="utf-8") as handle:
                metadata = json.load(handle)

        base_index = index
        if isinstance(index, faiss.IndexIDMap2):
            base_index = index.index

        dimension = int(metadata.get("dimension", getattr(base_index, "d", 0)))
        metric = int(metadata.get("metric", getattr(base_index, "metric_type", faiss.METRIC_INNER_PRODUCT)))
        hnsw_m = int(metadata.get("hnsw_m", HNSW_M))
        ef_construction = int(metadata.get("ef_construction", HNSW_EF_CONSTRUCTION))
        ef_search = int(metadata.get("ef_search", HNSW_EF_SEARCH))

        return cls(
            dimension=dimension,
            m=hnsw_m,
            metric=metric,
            ef_construction=ef_construction,
            ef_search=ef_search,
            index=index,
        )


def save_index(index: FaissIndexManager, path: Path | str) -> Path:
    """Save a FAISS index manager to disk."""

    return index.save_index(path)


def load_index(path: Path | str) -> FaissIndexManager:
    """Load a FAISS index manager from disk."""

    return FaissIndexManager.load_index(path)
