"""Cross-encoder reranking utilities for TalentRank Phase 3."""

from __future__ import annotations

import threading
from typing import Any

from fastapi import HTTPException
from sentence_transformers import CrossEncoder
import torch

from src.talentrank.config import CROSS_ENCODER_MODEL_NAME, get_settings

# Module-level: the cross-encoder is the scarce resource on a 2-vCPU box, so every
# request funnels through one bounded gate rather than forty threads fighting over
# two cores. Sized from settings at import time; tests override the module attribute
# directly rather than reconstructing it, since it must stay a true process-wide
# singleton in production.
_INFERENCE_SEMAPHORE = threading.BoundedSemaphore(get_settings().max_concurrent_inferences)


def _candidate_text(candidate: dict[str, Any]) -> str:
    """Job requirements live at the top of a posting, not in the trailing EEO
    paragraph -- truncating to `rerank_text_max_chars` loses little, and the model's
    own `max_length` would have discarded everything past ~512 tokens anyway."""

    text = candidate.get("job_text")
    if text is None:
        text = candidate.get("text")
    if text is None:
        text = candidate.get("description")
    normalized = " ".join(str(text).split())
    return normalized[: get_settings().rerank_text_max_chars]


@torch.inference_mode()
def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    top_n: int = 10,
    model: CrossEncoder | None = None,
    semaphore: threading.BoundedSemaphore | None = None,
) -> list[dict[str, Any]]:
    """Rerank candidate jobs with a cross-encoder score.

    `model` should normally come from `models.get_model_bundle().cross_encoder` so the
    process-wide singleton is reused. The `None` fallback (a fresh, uncached
    `CrossEncoder`) exists only for direct/offline callers -- it is not the path any
    request handler takes.

    The cross-encoder call itself is gated by `semaphore` (default: the module-level
    `_INFERENCE_SEMAPHORE`). `BoundedSemaphore.acquire(timeout=...)` returns `False`
    on timeout rather than raising, so a stalled queue is shed as a 503 instead of
    piling up requests behind a single CPU-bound model.
    """

    if top_n <= 0 or not candidates:
        return []

    ce = model or CrossEncoder(CROSS_ENCODER_MODEL_NAME, max_length=get_settings().cross_encoder_max_length)
    pairs = [[query, _candidate_text(candidate)] for candidate in candidates]

    sem = semaphore or _INFERENCE_SEMAPHORE
    if not sem.acquire(timeout=get_settings().inference_queue_timeout_seconds):
        raise HTTPException(503, detail="Server busy, please retry", headers={"Retry-After": "5"})
    try:
        scores = ce.predict(pairs)
    finally:
        sem.release()

    ranked_candidates = []
    for candidate, score in zip(candidates, scores):
        ranked_candidate = dict(candidate)
        ranked_candidate["cross_encoder_score"] = float(score)
        ranked_candidates.append(ranked_candidate)

    ranked_candidates.sort(key=lambda item: item["cross_encoder_score"], reverse=True)
    return ranked_candidates[:top_n]
