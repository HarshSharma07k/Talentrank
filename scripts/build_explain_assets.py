"""Offline builder for TalentRank's explainability IDF asset.

Computes inverse document frequency over the job corpus's `text` column using the
exact tokenizer `explain.py` uses at request time (`explain._explain_normalize` +
`explain._tokenize`) -- an IDF map built with a different tokenizer would silently
never match a token the live pipeline produces, since lookups are a plain dict `.get`
with no fuzzy fallback. Writes the top `_MAX_VOCAB_TERMS` terms by corpus frequency to
`settings.term_idf_path`.

Usage:
    python scripts/build_explain_assets.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.talentrank.config import get_settings  # noqa: E402
from src.talentrank.explain import _explain_normalize, _tokenize  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("build_explain_assets")

_MAX_VOCAB_TERMS = 50_000


def _analyzer(text: str) -> list[str]:
    """The same normalize-then-tokenize path `explain.py` runs per request."""

    return list(_tokenize(_explain_normalize(str(text))).keys())


def build_term_idf(texts: pd.Series, max_terms: int = _MAX_VOCAB_TERMS) -> dict[str, float]:
    """Smoothed IDF (`ln((1+n)/(1+df)) + 1`, the same formula sklearn's own
    `TfidfTransformer` uses) over the `max_terms` most frequent terms in `texts`.

    `CountVectorizer(binary=True)` gives a presence matrix per document; summing its
    columns is the document frequency `df` each term needs.
    """

    vectorizer = CountVectorizer(analyzer=_analyzer, max_features=max_terms, binary=True)
    matrix = vectorizer.fit_transform(texts)

    n_docs = matrix.shape[0]
    doc_freq = np.asarray(matrix.sum(axis=0)).ravel()
    idf = np.log((1 + n_docs) / (1 + doc_freq)) + 1.0

    return dict(zip(vectorizer.get_feature_names_out().tolist(), idf.tolist()))


def main() -> None:
    """Build and persist `term_idf.json` from the configured job corpus."""

    settings = get_settings()
    jobs_path = Path(settings.jobs_clean_path)
    if not jobs_path.exists():
        raise FileNotFoundError(
            f"Jobs parquet does not exist: {jobs_path}. Run scripts/prep_data.py and scripts/build_index.py first."
        )

    logger.info("Loading job corpus from %s", jobs_path)
    jobs = pd.read_parquet(jobs_path, columns=["text"])
    # Same cap the reranker and `explain.py` apply at request time -- an IDF built
    # over untruncated descriptions would weight terms that live only in text the
    # live pipeline never actually sees.
    capped_texts = jobs["text"].astype(str).str.slice(0, settings.rerank_text_max_chars)

    start = time.perf_counter()
    term_idf = build_term_idf(capped_texts)
    elapsed = time.perf_counter() - start

    term_idf_path = Path(settings.term_idf_path)
    term_idf_path.parent.mkdir(parents=True, exist_ok=True)
    with term_idf_path.open("w", encoding="utf-8") as f:
        json.dump(term_idf, f)

    logger.info(
        "Wrote %d terms to %s in %.1fs (%d job rows, %.1f KiB)",
        len(term_idf),
        term_idf_path,
        elapsed,
        len(jobs),
        term_idf_path.stat().st_size / 1024,
    )


if __name__ == "__main__":
    main()
