"""Regression tests for finding 3: the embedding cache used to leak on every
request, and `use_cache=False` did nothing about it (embeddings.py:187 called
`save_embeddings` unconditionally). See .claude/enhancements/00-overview.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.talentrank.embeddings import TextEmbeddingEncoder, build_text_fingerprint

if TYPE_CHECKING:
    from tests.conftest import StubBiEncoder


def _stubbed_encoder(cache_dir: Path, stub_bi_encoder: StubBiEncoder) -> TextEmbeddingEncoder:
    encoder = TextEmbeddingEncoder(cache_dir=cache_dir)
    encoder._model = stub_bi_encoder
    return encoder


def test_no_cache_writes_zero_files(tmp_path: Path, stub_bi_encoder: StubBiEncoder) -> None:
    cache_dir = tmp_path / "cache"
    encoder = _stubbed_encoder(cache_dir, stub_bi_encoder)

    encoder.encode_texts(["a resume about python"], use_cache=False, show_progress_bar=False)

    assert not cache_dir.exists() or list(cache_dir.iterdir()) == []


def test_no_mkdir_on_construction(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"

    TextEmbeddingEncoder(cache_dir=cache_dir)

    assert not cache_dir.exists()


def test_cache_roundtrip(tmp_path: Path, stub_bi_encoder: StubBiEncoder) -> None:
    cache_dir = tmp_path / "cache"
    encoder = _stubbed_encoder(cache_dir, stub_bi_encoder)
    texts = ["a resume about python", "a resume about nursing"]

    first = encoder.encode_texts(texts, use_cache=True, show_progress_bar=False)
    assert list(cache_dir.iterdir()) != []

    # Poison the model so a second real encode would raise; the round-trip must
    # come from the cache instead.
    encoder._model = None
    second = encoder.encode_texts(texts, use_cache=True, show_progress_bar=False)

    assert (first == second).all()


def test_fingerprint_stable() -> None:
    texts = ["a resume about python", "a resume about nursing"]

    first = build_text_fingerprint(texts, "some-model")
    second = build_text_fingerprint(texts, "some-model")

    assert first == second
