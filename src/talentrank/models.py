"""Model and corpus lifecycle for TalentRank.

`get_model_bundle()` is the single seam every request-handling code path loads
models and corpus artifacts through -- it replaces the old pattern of monkey-patching
module globals from `lifespan` and reading the FAISS index twice. See enhancements/03.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time

import pandas as pd
import torch
from functools import lru_cache
from pathlib import Path
from sentence_transformers import CrossEncoder, SentenceTransformer

from src.talentrank.config import get_settings
from src.talentrank.index import FaissIndexManager
from src.talentrank.schemas import JobFamilyCount

logger = logging.getLogger("talentrank.models")
if not logger.handlers:
    # See api.py's identical block: a scoped handler + propagate=False keeps this
    # visible without raising the root logger's level (which would flood the log
    # with third-party INFO records from httpx/huggingface_hub).
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

# Reused so `warmup()` and the demo-corpus cache-warm in enhancements/08 exercise the
# same query text as the frontend's "Load sample resume" button.
SAMPLE_RESUME = (
    "Backend engineer with 5 years of experience building machine learning services in "
    "Python. Designed and shipped a semantic search pipeline using sentence-transformers "
    "and FAISS for approximate nearest neighbor retrieval, serving results through a "
    "FastAPI application deployed on Docker. Comfortable with PyTorch, pandas, and "
    "scikit-learn for data preprocessing and model evaluation. Experience optimizing "
    "latency-sensitive services, including profiling with cProfile and reducing p50 "
    "response times through caching and vectorized pandas operations. Familiar with "
    "CI/CD pipelines, pytest for testing, and cloud deployment on AWS. Previously worked "
    "on a recommendation system that combined bi-encoder retrieval with cross-encoder "
    "reranking to improve relevance of search results."
)


@dataclass(slots=True)
class ModelBundle:
    """Everything a request needs to serve a match, loaded exactly once per process."""

    device: str
    bi_encoder: SentenceTransformer
    cross_encoder: CrossEncoder
    index: FaissIndexManager
    jobs: pd.DataFrame
    idf: dict[str, float]  # always {} until enhancements/04 builds term_idf.json
    families: list[JobFamilyCount]  # always [] until enhancements/05 + /09 add job_family
    loaded_at: float
    warm: bool = False


def _load_jobs_frame(jobs_clean_path: Path) -> pd.DataFrame:
    if not jobs_clean_path.exists():
        raise FileNotFoundError(f"Jobs parquet file does not exist: {jobs_clean_path}")

    df = pd.read_parquet(jobs_clean_path)
    df["job_id"] = df["job_id"].astype(str)
    df.set_index("job_id", inplace=True)
    return df


_QUANTIZE_SELF_TEST_PAIR = [["quantization self-test query", "quantization self-test passage"]]


def _quantize_module(cross_encoder: CrossEncoder) -> None:
    """Replace `cross_encoder.model`'s `Linear` layers with dynamic int8 quantized
    versions, in place. No validation -- callers must already know this is safe.
    Split out from `_quantize_cross_encoder` so the exact same call can run once
    against a disposable probe and, only if that succeeds, again against the real
    object, without duplicating the `quantize_dynamic` call itself.
    """

    inner_model = getattr(cross_encoder, "model", None)
    if inner_model is None:
        raise AttributeError("CrossEncoder.model is not available on this sentence-transformers version")
    cross_encoder.model = torch.quantization.quantize_dynamic(inner_model, {torch.nn.Linear}, dtype=torch.qint8)


def _quantize_cross_encoder(cross_encoder: CrossEncoder) -> None:
    """Apply dynamic int8 quantization to the live cross-encoder, behind
    `settings.cross_encoder_quantize` (default off) -- but only after validating it
    end-to-end on a disposable, independently-loaded probe instance first.

    Measured directly against this project's pinned versions (sentence-transformers
    5.5.1, transformers 5.10.2, torch 2.11.0): `torch.quantization.quantize_dynamic`
    runs without raising, but a subsequent `CrossEncoder.predict()` call raises deep
    inside `BertForSequenceClassification.forward` (`AttributeError` from a
    `BatchEncoding` reaching `.size()`) -- quantization is not merely slower or
    lower-quality here, it is non-functional.

    A first version of this function quantized the *live* `cross_encoder` directly,
    self-tested with `predict()`, and reassigned `cross_encoder.model` back to the
    pre-quantization object on failure. That rollback did not actually restore
    working behavior: a real request through the same (rolled-back) bundle during
    startup `warmup()` crashed the process anyway with the identical error --
    whatever this incompatibility corrupts is not confined to the `.model`
    reference, so reassigning it back is not sufficient. This version never mutates
    the live object at all unless an independent probe -- a second `CrossEncoder`
    loaded from the same (already-cached-locally) weights -- has already gone
    through the exact same quantize-then-predict sequence and survived it. A failed
    probe is therefore a universal verdict on this library/version combination, not
    an instance-specific fluke, so skipping the live object entirely on failure is
    the only presently-known-safe behavior. Costs one extra local model load
    (roughly a second, no network fetch) only when the flag is set.
    """

    settings = get_settings()
    try:
        probe = CrossEncoder(settings.cross_encoder_model_name, max_length=settings.cross_encoder_max_length)
        _quantize_module(probe)
        probe.predict(_QUANTIZE_SELF_TEST_PAIR)
    except Exception:
        logger.warning(
            "cross_encoder_quantize is set but quantization failed its self-test on an isolated "
            "probe instance against the installed sentence-transformers/torch versions; the live "
            "cross-encoder was left untouched, continuing unquantized.",
            exc_info=True,
        )
        return

    _quantize_module(cross_encoder)


@lru_cache(maxsize=1)
def get_model_bundle() -> ModelBundle:
    """Load models, the FAISS index, and the jobs frame once. `functools.lru_cache`
    does not cache an exception, so a `FileNotFoundError` here (missing `data/processed/`)
    is safe to retry on the next call rather than wedging the process in a failed state.
    """

    settings = get_settings()
    device = "cuda" if torch.cuda.is_available() else "cpu"

    bi_encoder = SentenceTransformer(settings.bi_encoder_model_name, device=device)
    cross_encoder = CrossEncoder(
        settings.cross_encoder_model_name, device=device, max_length=settings.cross_encoder_max_length
    )
    if settings.cross_encoder_quantize:
        _quantize_cross_encoder(cross_encoder)

    index_path = Path(settings.job_index_path)
    if not index_path.exists():
        raise FileNotFoundError(f"FAISS index file does not exist: {index_path}")
    logger.info("Loading FAISS index from %s", index_path)
    index = FaissIndexManager.load_index(index_path)

    jobs = _load_jobs_frame(Path(settings.jobs_clean_path))

    return ModelBundle(
        device=device,
        bi_encoder=bi_encoder,
        cross_encoder=cross_encoder,
        index=index,
        jobs=jobs,
        idf={},
        families=[],
        loaded_at=time.monotonic(),
        warm=False,
    )


def warmup(bundle: ModelBundle) -> None:
    """Run one real match so the first user request doesn't pay lazy-init cost.

    Goes through `cached_match`, not `match`, so this also populates the result
    cache for `SAMPLE_RESUME` at the default `top_k`/`top_n` -- the frontend's "Load
    sample resume" -> "Find matching jobs" click sends exactly this text with no
    filters, so the single most likely interview demo click becomes a cache hit
    instead of paying the full rerank cost. See enhancements/08.
    """

    from src.talentrank.pipeline import cached_match

    settings = get_settings()
    cached_match(SAMPLE_RESUME, top_k=settings.default_top_k, top_n=settings.default_top_n, bundle=bundle)
    bundle.warm = True
