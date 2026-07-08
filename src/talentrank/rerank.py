"""Cross-encoder reranking utilities for TalentRank Phase 3."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sentence_transformers import CrossEncoder

from src.talentrank.config import CROSS_ENCODER_MODEL_NAME


DEFAULT_CROSS_ENCODER_MODEL: CrossEncoder | None = None


def _candidate_text(candidate: dict[str, Any]) -> str:
    text = candidate.get("job_text")
    if text is None:
        text = candidate.get("text")
    if text is None:
        text = candidate.get("description")
    return " ".join(str(text).split())


@lru_cache(maxsize=1)
def _load_cross_encoder() -> CrossEncoder:
    if DEFAULT_CROSS_ENCODER_MODEL is not None:
        return DEFAULT_CROSS_ENCODER_MODEL
    return CrossEncoder(CROSS_ENCODER_MODEL_NAME)


def rerank(query: str, candidates: list[dict[str, Any]], top_n: int = 10) -> list[dict[str, Any]]:
    """Rerank candidate jobs with a cross-encoder score."""

    if top_n <= 0 or not candidates:
        return []

    pairs = [[query, _candidate_text(candidate)] for candidate in candidates]
    scores = _load_cross_encoder().predict(pairs)

    ranked_candidates = []
    for candidate, score in zip(candidates, scores):
        ranked_candidate = dict(candidate)
        ranked_candidate["cross_encoder_score"] = float(score)
        ranked_candidates.append(ranked_candidate)

    ranked_candidates.sort(key=lambda item: item["cross_encoder_score"], reverse=True)
    return ranked_candidates[:top_n]