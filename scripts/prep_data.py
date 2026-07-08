"""Run phase 1 data preparation for TalentRank."""

from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.talentrank.data import prepare_phase_one_data


def main() -> None:
    """Prepare cleaned corpora and print a compact summary."""

    result = prepare_phase_one_data()
    pairs = result.pairs
    coverage = float(pairs["relevance"].mean()) if not pairs.empty else 0.0

    print(f"Corpus size (N): {len(pairs):,}")
    print(f"Label coverage: {coverage:.2%}")
    print("Sample rows:")

    sample_columns = ["resume_id", "resume_category", "job_id", "job_title", "relevance"]
    sample_frame = pairs[sample_columns].head(3) if len(pairs) <= 3 else pairs[sample_columns].sample(n=3, random_state=42)
    print(sample_frame.to_string(index=False))
    print(f"Saved pairs: {result.pairs_path}")
    print(f"Saved train split: {result.train_path}")
    print(f"Saved eval split: {result.eval_path}")


if __name__ == "__main__":
    main()