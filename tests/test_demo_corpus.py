"""Tests for `scripts/build_demo_corpus.py`. See enhancements/09."""

from __future__ import annotations

import pandas as pd

from scripts.build_demo_corpus import build_demo_frame, stratified_sample


def _synthetic_jobs(family_sizes: dict[str, int]) -> pd.DataFrame:
    """A minimal frame with the columns `stratified_sample`/`build_demo_frame` need,
    with `job_family` assigned directly rather than derived -- this suite tests the
    sampling and text-rebuild logic in isolation, not `derive_job_family` (see
    `test_filters.py` for that)."""

    rows = []
    job_id = 1
    for family, size in family_sizes.items():
        for i in range(size):
            rows.append(
                {
                    "job_id": job_id,
                    "job_title": f"{family} Role {i}",
                    "description": f"Description for {family} role number {i} in this synthetic corpus.",
                    "skills": "",
                    "text": f"stale placeholder text {family} {i}",
                    "job_category": family,
                    "job_family": family,
                }
            )
            job_id += 1
    return pd.DataFrame(rows)


def test_per_family_floor() -> None:
    """A family with only 3 rows keeps all 3, even though its proportional share of
    a 100-row target from a 1003-row corpus would round to near zero."""

    jobs = _synthetic_jobs({"BIG": 1000, "RARE": 3})

    sampled = stratified_sample(jobs, target_size=100, floor=200, random_state=42)

    assert len(sampled[sampled["job_family"] == "RARE"]) == 3


def test_output_size_within_tolerance() -> None:
    """With three equally-sized families, each family's proportional share is well
    above the floor, so the total lands close to the requested target."""

    jobs = _synthetic_jobs({"A": 500, "B": 500, "C": 500})

    sampled = stratified_sample(jobs, target_size=300, floor=50, random_state=42)

    assert 250 <= len(sampled) <= 350


def test_job_ids_unique() -> None:
    jobs = _synthetic_jobs({"A": 200, "B": 200, "C": 5})

    sampled = stratified_sample(jobs, target_size=100, floor=50, random_state=42)

    assert sampled["job_id"].is_unique


def test_text_rebuilt_from_truncated_fields() -> None:
    """The regression test for enhancements/09 step 4's critical invariant: `text`
    must be rebuilt from the *truncated* description, not the original. Content
    that only exists past the truncation point must never appear in `text`."""

    description = ("x" * 100) + " zzzsecretmarker"
    jobs = pd.DataFrame(
        {
            "job_id": [1],
            "job_title": ["Software Engineer"],
            "description": [description],
            "skills": ["python"],
            "text": ["stale placeholder text that must not survive"],
            "job_category": ["SOFTWARE-ENGINEER"],
            "job_family": ["ENGINEERING"],
        }
    )

    demo = build_demo_frame(jobs, target_size=1, floor=1, description_max_chars=50, random_state=42)

    row = demo.iloc[0]
    assert len(row["description"]) == 50
    assert "zzzsecretmarker" not in row["text"]
    assert "stale placeholder" not in row["text"]
    assert "software" in row["text"]  # the title survives the rebuild


def test_build_demo_frame_derives_job_family_if_missing() -> None:
    jobs = pd.DataFrame(
        {
            "job_id": [1, 2],
            "job_title": ["Registered Nurse", "Sales Associate"],
            "description": ["Nursing role.", "Sales role."],
            "skills": ["", ""],
            "text": ["placeholder", "placeholder"],
            "job_category": ["REGISTERED-NURSE", "SALES-ASSOCIATE"],
        }
    )

    demo = build_demo_frame(jobs, target_size=2, floor=1, description_max_chars=100, random_state=42)

    assert set(demo["job_family"]) == {"HEALTHCARE", "SALES"}
