"""Phase 3 retrieval and reranking pipeline for TalentRank."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from typing import TYPE_CHECKING, Any, Literal

from src.talentrank.cache import get_cache_backend
from src.talentrank.config import DEFAULT_TOP_K, DEFAULT_TOP_N, get_settings
from src.talentrank.embeddings import TextEmbeddingEncoder
from src.talentrank.explain import build_resume_terms, explain_candidate
from src.talentrank.filters import apply_filters
from src.talentrank.models import get_model_bundle
from src.talentrank.rerank import rerank
from src.talentrank.schemas import Explanation, JobMatch, MatchFilters, MatchResponse, ScoreBreakdown

if TYPE_CHECKING:
    import pandas as pd

    from src.talentrank.models import ModelBundle

logger = logging.getLogger("talentrank.pipeline")
if not logger.handlers:
    # See api.py's identical block: a scoped handler + propagate=False keeps this
    # visible without raising the root logger's level.
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _resolve_job_row(jobs: pd.DataFrame, job_id: int) -> dict[str, Any] | None:
    str_id = str(job_id)

    # Instant hash-map lookup
    if str_id not in jobs.index:
        return None

    row = jobs.loc[str_id].to_dict()
    row["job_id"] = int(job_id)
    return row


def retrieve_only(resume_text: str, top_k: int, bundle: ModelBundle | None = None) -> list[dict[str, Any]]:
    """Retrieve the top_k jobs with bi-encoder scores only."""

    if top_k <= 0:
        return []

    query_text = " ".join(str(resume_text).split())
    if not query_text:
        return []

    bundle = bundle or get_model_bundle()

    encoder = TextEmbeddingEncoder(model=bundle.bi_encoder)
    query_embedding = encoder.encode_texts([query_text], use_cache=False, show_progress_bar=False)[0]

    hits = bundle.index.search(query_embedding, k=top_k)
    jobs = bundle.jobs

    candidates: list[dict[str, Any]] = []
    for retrieval_rank, hit in enumerate(hits, start=1):
        job_row = _resolve_job_row(jobs, hit.job_id)
        if job_row is None:
            continue

        job_row["job_text"] = job_row.get("text", "")
        job_row["bi_encoder_score"] = float(hit.score)
        job_row["retrieval_rank"] = retrieval_rank
        candidates.append(job_row)

    return candidates


def match(
    resume_text: str,
    top_k: int = DEFAULT_TOP_K,
    top_n: int = DEFAULT_TOP_N,
    bundle: ModelBundle | None = None,
) -> list[dict[str, Any]]:
    """Retrieve candidates and rerank them with the cross-encoder.

    `bundle` is resolved as late as possible -- only once we know reranking will
    actually run (`rerank` itself is a no-op for `top_n <= 0` or no candidates) -- so
    a degenerate call (empty resume, `top_k`/`top_n` <= 0) never forces a real model
    load. This matters for tests: `retrieve_only`'s own early-exit guards mean a call
    like `match("", top_k=0)` must stay entirely free of `get_model_bundle()`.
    """

    candidates = retrieve_only(resume_text=resume_text, top_k=top_k, bundle=bundle)
    if top_n <= 0 or not candidates:
        return []

    bundle = bundle or get_model_bundle()
    return rerank(query=resume_text, candidates=candidates, top_n=top_n, model=bundle.cross_encoder)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _to_job_match(
    candidate: dict[str, Any],
    rank: int,
    cross_encoder_score: float,
    explanation: Explanation | None = None,
) -> JobMatch:
    settings = get_settings()
    bi_encoder_score = float(candidate.get("bi_encoder_score", 0.0))
    description = str(candidate.get("description", ""))[: settings.description_max_chars]
    skill_overlap = explanation.overlap_score if explanation is not None else 0.0

    return JobMatch(
        job_id=int(candidate["job_id"]),
        job_title=str(candidate.get("job_title", "")),
        description=description,
        skills=str(candidate.get("skills", "") or ""),
        job_category=str(candidate.get("job_category", "")),
        job_family=str(candidate.get("job_family") or "OTHER"),
        bi_encoder_score=bi_encoder_score,
        cross_encoder_score=cross_encoder_score,
        scores=ScoreBreakdown(
            bi_encoder=bi_encoder_score,
            cross_encoder=cross_encoder_score,
            cross_encoder_probability=_sigmoid(cross_encoder_score),
            skill_overlap=skill_overlap,
        ),
        explanation=explanation,
        retrieval_rank=int(candidate.get("retrieval_rank", rank)),
        rank=rank,
    )


def _build_match_response(
    results: list[JobMatch],
    stage: Literal["retrieve", "rerank"],
    top_k: int,
    top_n: int,
    total_candidates: int,
    filtered_candidates: int,
    took_ms: float,
    cached: bool,
    bundle: ModelBundle,
) -> MatchResponse:
    return MatchResponse(
        results=results,
        stage=stage,
        top_k=top_k,
        top_n=top_n,
        total_candidates=total_candidates,
        filtered_candidates=filtered_candidates,
        took_ms=took_ms,
        cached=cached,
        corpus_size=len(bundle.jobs),
    )


def _effective_retrieval_top_k(top_k: int, filters: MatchFilters | None) -> int:
    """Over-fetch from FAISS only when a family filter is active (enhancements/05).

    A family filter applied *after* a plain `top_k` retrieval would routinely narrow
    the shortlist to a handful of candidates (or zero, for a sparse family like
    AGRICULTURE) before rerank ever runs. Over-fetching by `filter_overfetch_factor`
    gives the family filter a large-enough pool to survive on. `min_score` does not
    trigger over-fetch: it depends on `cross_encoder_score`, which does not exist
    until after rerank, so there is nothing to over-fetch for at retrieval time.
    """

    if filters is not None and filters.job_families:
        return top_k * get_settings().filter_overfetch_factor
    return top_k


def retrieve_response(resume_text: str, top_k: int, top_n: int, bundle: ModelBundle | None = None) -> MatchResponse:
    """Stage 1 only: bi-encoder retrieval, no reranking, never cached. Fast -- the
    progressive-UI enabler."""

    bundle = bundle or get_model_bundle()
    start = time.perf_counter()
    candidates = retrieve_only(resume_text, top_k=top_k, bundle=bundle)
    page = candidates[:top_n]
    results = [_to_job_match(c, rank=i, cross_encoder_score=0.0) for i, c in enumerate(page, start=1)]

    return _build_match_response(
        results,
        stage="retrieve",
        top_k=top_k,
        top_n=top_n,
        total_candidates=len(candidates),
        filtered_candidates=len(candidates),  # /retrieve never filters -- see enhancements/05
        took_ms=(time.perf_counter() - start) * 1000,
        cached=False,
        bundle=bundle,
    )


def match_response(
    resume_text: str,
    top_k: int,
    top_n: int,
    bundle: ModelBundle | None = None,
    explain: bool = True,
    filters: MatchFilters | None = None,
) -> MatchResponse:
    """Stage 2: retrieval + cross-encoder rerank, uncached. `cached_match` is the
    cache-fronted wrapper around this -- call this directly only to bypass the cache.

    `explain` gates the lexical evidence layer (enhancements/04). It runs only on the
    `top_n` reranked results, never the `top_k` shortlist, and only when set -- so
    `/retrieve` and eval/benchmark call sites can skip it entirely.

    `filters` (enhancements/05) is applied twice through the same `apply_filters`
    call, once on each side of rerank: family filtering before (so a filtered-out
    candidate never pays for a cross-encoder pass), min-score filtering after (it
    needs `cross_encoder_score`, which only exists post-rerank). See `filters.py`'s
    docstring for why one function is safe to call at both points. `top_k` itself is
    over-fetched from FAISS when a family filter is active -- see
    `_effective_retrieval_top_k`.
    """

    bundle = bundle or get_model_bundle()
    active_filters = filters if filters is not None else MatchFilters()
    start = time.perf_counter()

    retrieval_top_k = _effective_retrieval_top_k(top_k, active_filters)
    candidates = retrieve_only(resume_text, top_k=retrieval_top_k, bundle=bundle)
    total_candidates = len(candidates)

    family_filtered = apply_filters(candidates, active_filters)
    ranked_all = rerank(
        query=resume_text, candidates=family_filtered, top_n=len(family_filtered), model=bundle.cross_encoder
    )
    score_filtered = apply_filters(ranked_all, active_filters)
    filtered_candidates = len(score_filtered)
    ranked = score_filtered[:top_n]

    resume_terms = build_resume_terms(resume_text) if explain and ranked else None
    results = [
        _to_job_match(
            c,
            rank=i,
            cross_encoder_score=float(c.get("cross_encoder_score", 0.0)),
            explanation=explain_candidate(resume_terms, c, bundle.idf) if resume_terms is not None else None,
        )
        for i, c in enumerate(ranked, start=1)
    ]

    return _build_match_response(
        results,
        stage="rerank",
        top_k=top_k,
        top_n=top_n,
        total_candidates=total_candidates,
        filtered_candidates=filtered_candidates,
        took_ms=(time.perf_counter() - start) * 1000,
        cached=False,
        bundle=bundle,
    )


def _filters_digest(filters: MatchFilters | None) -> str:
    payload = filters.model_dump() if filters is not None else {}
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:8]


def cached_match(
    resume_text: str,
    top_k: int,
    top_n: int,
    filters: MatchFilters | None = None,
    bundle: ModelBundle | None = None,
    explain: bool = True,
) -> MatchResponse:
    """`match_response()`, fronted by the process cache. The only call site that
    touches the cache -- see enhancements/07.

    Key: `match:v1:{sha256(resume_text)[:16]}:{top_k}:{top_n}:{filters_digest}:{explain}`.
    The `v1` prefix is deliberate: bump it to invalidate everything when a model, the
    corpus profile, or the scoring changes. `explain` is part of the key (not just an
    argument to the uncached path) because it changes the response shape -- a hit
    from a request that skipped explanations must never be replayed to one that
    asked for them. The hash is over whitespace-normalized text -- the same
    normalization `retrieve_only` applies before embedding -- so two requests that
    are byte-different only in incidental whitespace (a common way for a pasted
    resume, or a frontend template literal, to drift from a backend constant) still
    collide on the same cache key. This is what makes `warmup`'s cache-warm of
    `SAMPLE_RESUME` (enhancements/08) actually reliable rather than contingent on two
    source files staying character-for-character identical.

    Both `get` and `set` are guarded here: a cache backend outage must degrade the
    service to slow, never to a 500.
    """

    settings = get_settings()
    cache = get_cache_backend()
    normalized_text = " ".join(str(resume_text).split())
    resume_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:16]
    key = f"match:v1:{resume_hash}:{top_k}:{top_n}:{_filters_digest(filters)}:{int(explain)}"

    start = time.perf_counter()
    cached_bytes: bytes | None = None
    try:
        cached_bytes = cache.get(key)
    except Exception:
        logger.debug("Cache backend get() failed; serving uncached.")

    if cached_bytes is not None:
        # `took_ms` on a stored response describes the original (uncached) compute --
        # replaying it on a hit would misreport a near-instant cache lookup as an
        # 800ms rerank pass. Overwrite it with this call's actual elapsed time.
        response = MatchResponse.model_validate_json(cached_bytes)
        response.cached = True
        response.took_ms = (time.perf_counter() - start) * 1000
        return response

    response = match_response(resume_text, top_k=top_k, top_n=top_n, bundle=bundle, explain=explain, filters=filters)

    try:
        cache.set(key, response.model_dump_json().encode("utf-8"), ttl_seconds=settings.cache_ttl_seconds)
    except Exception:
        logger.debug("Cache backend set() failed; result not cached.")

    return response
