"""Offline builder for TalentRank's stratified demo corpus. See enhancements/09.

The full corpus (`jobs.faiss` 214.5 MiB + `jobs_clean.parquet` 418.3 MiB, measured
2026-08-08) is too large for the hosted HF Space's free tier -- a ~633 MiB image
layer before model weights, plus the RAM to hold the frame. This script produces a
stratified ~25k-row subsample instead, proportional to each job_family's share of the
full corpus but with a per-family floor so rare families (AGRICULTURE, AVIATION)
don't vanish and make the demo look tech-only, which the measured distribution shows
it is not.

Usage:
    python scripts/build_demo_corpus.py [--size 25000] [--out data/demo]
    python scripts/build_index.py --jobs-path data/demo/jobs_demo.parquet \
                                  --index-path data/demo/jobs_demo.faiss
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.talentrank.config import get_settings  # noqa: E402
from src.talentrank.data import _combine_text, derive_job_family  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("build_demo_corpus")

# "Roughly min(len(family), 200)" per enhancements/09 step 2 -- without this floor,
# a naive proportional split at ~25k/123,849 rounds AGRICULTURE (72 rows) and
# AVIATION (174) down toward zero, and the explainability feature (enhancements/04)
# would have nothing non-tech to demonstrate against in the hosted demo.
_PER_FAMILY_FLOOR = 200


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for offline demo corpus construction."""

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Build TalentRank's stratified demo corpus.")
    parser.add_argument("--size", type=int, default=settings.demo_corpus_size, help="Target row count.")
    parser.add_argument(
        "--jobs-path",
        type=Path,
        default=settings.processed_data_dir / "jobs_clean.parquet",
        help="Path to the cleaned full-corpus jobs parquet file.",
    )
    parser.add_argument(
        "--out", type=Path, default=settings.data_dir / "demo", help="Output directory for the demo parquet."
    )
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def stratified_sample(jobs: pd.DataFrame, target_size: int, floor: int, random_state: int) -> pd.DataFrame:
    """Sample `jobs` proportional to each `job_family`'s share of the corpus, with a
    per-family floor of `min(len(family), floor)`.

    An explicit per-group loop, not `groupby(...).apply(...)`: this code runs once,
    offline, and pandas 3.0's copy-on-write semantics changed `apply` well enough
    that clarity here beats brevity. `job_id` values are preserved as-is (never
    reset), since the FAISS index built from this frame must key on the same IDs.
    """

    total = len(jobs)
    sampled_frames: list[pd.DataFrame] = []

    for _family, group in jobs.groupby("job_family", sort=False):
        proportional_share = round(target_size * len(group) / total)
        family_size = min(len(group), max(proportional_share, floor))
        sampled_frames.append(group.sample(n=family_size, random_state=random_state))

    return pd.concat(sampled_frames, ignore_index=True)


def build_demo_frame(
    jobs: pd.DataFrame, target_size: int, floor: int, description_max_chars: int, random_state: int
) -> pd.DataFrame:
    """Derive `job_family` if missing, stratified-sample, truncate `description`, and
    **rebuild `text` from the truncated fields**.

    That rebuild is the critical invariant (enhancements/09 step 4): the FAISS index
    is built by embedding `job_title + " " + text` (`build_index.py`), and the
    cross-encoder reranks against `text` capped at `rerank_text_max_chars`
    (`rerank.py`). If `text` still held the untruncated description while the index
    were built from something else, retrieval and reranking would silently disagree
    about what a candidate even says.
    """

    frame = jobs.copy()
    if "job_family" not in frame.columns:
        frame["job_family"] = frame["job_title"].map(derive_job_family)

    sampled = stratified_sample(frame, target_size=target_size, floor=floor, random_state=random_state)

    sampled["description"] = sampled["description"].fillna("").astype(str).str.slice(0, description_max_chars)
    sampled["text"] = sampled.apply(
        lambda row: _combine_text([row["job_title"], row["description"], row.get("skills", "")]), axis=1
    )

    return sampled.reset_index(drop=True)


def main() -> None:
    """Build and persist `jobs_demo.parquet` from the full cleaned corpus."""

    args = parse_args()
    settings = get_settings()

    if not args.jobs_path.exists():
        raise FileNotFoundError(f"Jobs parquet does not exist: {args.jobs_path}. Run scripts/prep_data.py first.")

    logger.info("Loading full corpus from %s", args.jobs_path)
    jobs = pd.read_parquet(args.jobs_path)

    demo = build_demo_frame(
        jobs,
        target_size=args.size,
        floor=_PER_FAMILY_FLOOR,
        description_max_chars=settings.description_max_chars,
        random_state=args.random_state,
    )

    if demo["job_id"].duplicated().any():
        raise ValueError("Sampled demo frame has duplicate job_id values -- the FAISS index build would collide.")

    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "jobs_demo.parquet"
    demo.to_parquet(out_path, index=False)

    logger.info(
        "Wrote %d rows (of %d requested) to %s (%.1f MiB)",
        len(demo),
        args.size,
        out_path,
        out_path.stat().st_size / 1048576,
    )
    logger.info("Family distribution:\n%s", demo["job_family"].value_counts().to_string())
    logger.info(
        "Next: python scripts/build_index.py --jobs-path %s --index-path %s", out_path, args.out / "jobs_demo.faiss"
    )


if __name__ == "__main__":
    main()
