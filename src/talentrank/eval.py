"""Evaluation utilities for TalentRank."""

from __future__ import annotations

from sklearn.metrics import ndcg_score


def calculate_ndcg(true_labels: list[int], predicted_scores: list[float], k: int = 10) -> float:
    """Compute NDCG@k for a single ranked list."""

    return float(ndcg_score([true_labels], [predicted_scores], k=k))