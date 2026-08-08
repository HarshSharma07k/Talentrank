"""Embedding utilities for TalentRank Phase 2."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from src.talentrank.config import BI_ENCODER_MODEL_NAME, EMBEDDINGS_CACHE_DIR, EMBEDDING_BATCH_SIZE

try:
    from safetensors.numpy import load_file as load_safetensors_file
    from safetensors.numpy import save_file as save_safetensors_file
except ImportError:  # pragma: no cover - optional dependency
    load_safetensors_file = None
    save_safetensors_file = None


@dataclass(slots=True)
class EmbeddingCacheRecord:
    """Metadata for a cached embedding matrix."""

    fingerprint: str
    model_name: str
    text_count: int
    cache_format: str
    embedding_path: Path
    metadata_path: Path


def _normalize_text(text: object) -> str:
    if text is None:
        return ""
    return " ".join(str(text).split())


def build_text_fingerprint(texts: Sequence[str], model_name: str) -> str:
    """Build a stable fingerprint for a sequence of texts and model name."""

    digest = hashlib.sha256()
    digest.update(model_name.encode("utf-8"))
    digest.update(len(texts).to_bytes(8, byteorder="little", signed=False))

    for text in texts:
        normalized = _normalize_text(text)
        encoded = normalized.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, byteorder="little", signed=False))
        digest.update(encoded)

    return digest.hexdigest()


def _cache_record_from_fingerprint(cache_dir: Path, fingerprint: str) -> EmbeddingCacheRecord:
    safetensors_path = cache_dir / f"{fingerprint}.safetensors"
    numpy_path = cache_dir / f"{fingerprint}.npy"
    metadata_path = cache_dir / f"{fingerprint}.json"

    if safetensors_path.exists():
        return EmbeddingCacheRecord(fingerprint, "", 0, "safetensors", safetensors_path, metadata_path)
    return EmbeddingCacheRecord(fingerprint, "", 0, "numpy", numpy_path, metadata_path)


class TextEmbeddingEncoder:
    """Batch encoder with on-disk caching for job description embeddings."""

    def __init__(
        self,
        model_name: str = BI_ENCODER_MODEL_NAME,
        cache_dir: Path | None = None,
        model: SentenceTransformer | None = None,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = Path(cache_dir) if cache_dir is not None else EMBEDDINGS_CACHE_DIR
        self._model = model

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def cache_record(self, texts: Sequence[str]) -> EmbeddingCacheRecord:
        fingerprint = build_text_fingerprint(texts, self.model_name)
        record = _cache_record_from_fingerprint(self.cache_dir, fingerprint)
        metadata_path = self.cache_dir / f"{fingerprint}.json"
        return EmbeddingCacheRecord(
            fingerprint=fingerprint,
            model_name=self.model_name,
            text_count=len(texts),
            cache_format=record.cache_format,
            embedding_path=record.embedding_path,
            metadata_path=metadata_path,
        )

    def load_cached_embeddings(self, texts: Sequence[str]) -> np.ndarray | None:
        """Load cached embeddings for the current text sequence if available."""

        record = self.cache_record(texts)
        if not record.embedding_path.exists() or not record.metadata_path.exists():
            return None

        with record.metadata_path.open("r", encoding="utf-8") as handle:
            metadata = json.load(handle)

        if metadata.get("fingerprint") != record.fingerprint:
            return None
        if metadata.get("model_name") != self.model_name:
            return None
        if int(metadata.get("text_count", -1)) != len(texts):
            return None

        if record.cache_format == "safetensors":
            if load_safetensors_file is None:
                return None
            data = load_safetensors_file(record.embedding_path)
            embeddings = data["embeddings"]
        else:
            embeddings = np.load(record.embedding_path, mmap_mode="r")

        return np.asarray(embeddings, dtype=np.float32)

    def save_embeddings(self, texts: Sequence[str], embeddings: np.ndarray) -> EmbeddingCacheRecord:
        """Persist embeddings and metadata for the provided text sequence."""

        record = self.cache_record(texts)
        record.embedding_path.parent.mkdir(parents=True, exist_ok=True)
        matrix = np.asarray(embeddings, dtype=np.float32)
        numpy_path = self.cache_dir / f"{record.fingerprint}.npy"

        metadata = {
            "fingerprint": record.fingerprint,
            "model_name": self.model_name,
            "text_count": len(texts),
            "embedding_shape": list(matrix.shape),
            "embedding_dtype": str(matrix.dtype),
            "cache_format": record.cache_format,
        }

        if record.cache_format == "safetensors" and save_safetensors_file is not None:
            save_safetensors_file({"embeddings": matrix}, str(record.embedding_path))
        else:
            np.save(numpy_path, matrix)
            record = EmbeddingCacheRecord(
                fingerprint=record.fingerprint,
                model_name=self.model_name,
                text_count=len(texts),
                cache_format="numpy",
                embedding_path=numpy_path,
                metadata_path=record.metadata_path,
            )

        with record.metadata_path.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)

        return record

    def encode_texts(
        self,
        texts: Sequence[str],
        batch_size: int = EMBEDDING_BATCH_SIZE,
        use_cache: bool = False,
        show_progress_bar: bool = True,
    ) -> np.ndarray:
        """Encode texts into L2-normalized embeddings, using the cache when possible."""

        normalized_texts = [_normalize_text(text) for text in texts]
        if use_cache:
            cached_embeddings = self.load_cached_embeddings(normalized_texts)
            if cached_embeddings is not None:
                return cached_embeddings

        embeddings = self.model.encode(
            normalized_texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=show_progress_bar,
        )
        embeddings = np.asarray(embeddings, dtype=np.float32)
        if use_cache:
            self.save_embeddings(normalized_texts, embeddings)
        return embeddings


def encode_texts(
    texts: Sequence[str],
    model_name: str = BI_ENCODER_MODEL_NAME,
    cache_dir: Path | None = None,
    batch_size: int = EMBEDDING_BATCH_SIZE,
    use_cache: bool = False,
    show_progress_bar: bool = True,
) -> np.ndarray:
    """Convenience wrapper for batch encoding text into normalized embeddings."""

    encoder = TextEmbeddingEncoder(model_name=model_name, cache_dir=cache_dir)
    return encoder.encode_texts(
        texts=texts,
        batch_size=batch_size,
        use_cache=use_cache,
        show_progress_bar=show_progress_bar,
    )
