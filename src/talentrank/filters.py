"""Server-side result filtering for TalentRank matches. See enhancements/05.

Filtering happens server-side, not client-side: a client-side filter applied after
`top_n` slicing would routinely leave a couple of results on screen for anything but
the most common family. `apply_filters` is deliberately the single entry point for
both filter stages in `pipeline.py` -- called once before rerank (where only the
family filter has any effect, since no candidate carries `cross_encoder_score` yet)
and once after (where the min-score filter also applies). See its own docstring.
"""

from __future__ import annotations

import math
from typing import Any

from src.talentrank.schemas import MatchFilters


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def apply_filters(candidates: list[dict[str, Any]], filters: MatchFilters) -> list[dict[str, Any]]:
    """Apply the family and minimum-score filters, in that order.

    Safe to call at two different pipeline stages with the same `filters` object:
    - **Before rerank**, on retrieved candidates: the family filter applies (every
      candidate already carries `job_family` from the jobs frame); the min-score
      filter is a structural no-op because `"cross_encoder_score" not in candidate`
      is true for every candidate, not because the threshold happened to pass.
    - **After rerank**, on scored candidates: the family filter is a no-op (already
      filtered), and the min-score filter now applies for real, checked against
      `cross_encoder_probability` (`sigmoid(cross_encoder_score)`), never the raw
      logit -- a logit has no fixed [0, 1] range, so a `min_score` threshold only
      means anything against the sigmoid.
    """

    results = candidates

    if filters.job_families:
        wanted = set(filters.job_families)
        results = [c for c in results if c.get("job_family") in wanted]

    if filters.min_score is not None:
        threshold = filters.min_score
        results = [
            c
            for c in results
            if "cross_encoder_score" not in c or _sigmoid(float(c["cross_encoder_score"])) >= threshold
        ]

    return results
