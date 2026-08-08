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


def _quantize_cross_encoder(cross_encoder: CrossEncoder) -> None:
    """Apply dynamic int8 quantization to the cross-encoder's `Linear` layers, in
    place, behind `settings.cross_encoder_quantize` (default off).

    The `CrossEncoder.model` attribute path is version-specific in
    sentence-transformers, per enhancements/08's own risk note -- verified here by
    construction (`getattr` with a `None` default) rather than assumed. Measured
    directly against this project's pinned versions (sentence-transformers 5.5.1,
    transformers 5.10.2, torch 2.11.0): `torch.quantization.quantize_dynamic` runs
    without raising and returns a same-shaped module, but a subsequent
    `CrossEncoder.predict()` call raises deep inside
    `BertForSequenceClassification.forward` (`AttributeError` from a `BatchEncoding`
    object reaching `.size()`) -- quantization is not merely slower or lower-quality
    here, it is non-functional. The self-test below is therefore load-bearing, not
    speculative: it is the only thing standing between `cross_encoder_quantize=True`
    and every subsequent request 500ing.
    """

    inner_model = getattr(cross_encoder, "model", None)
    if inner_model is None:
        logger.warning("cross_encoder_quantize is set but CrossEncoder.model is unavailable; skipping quantization.")
        return

    try:
        quantized = torch.quantization.quantize_dynamic(inner_model, {torch.nn.Linear}, dtype=torch.qint8)
        cross_encoder.model = quantized
        cross_encoder.predict(_QUANTIZE_SELF_TEST_PAIR)
    except Exception:
        cross_encoder.model = inner_model
        logger.warning(
            "cross_encoder_quantize is set but quantization failed its self-test against the "
            "installed sentence-transformers/torch versions; continuing unquantized.",
            exc_info=True,
        )


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
