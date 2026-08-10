"""Phase 1 data preparation utilities for TalentRank."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
import unicodedata
from pathlib import Path
from typing import Iterable

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit, train_test_split

from src.talentrank.config import PROCESSED_DATA_DIR, RAW_DATA_DIR


JOB_SOURCE_CANDIDATES = (
    RAW_DATA_DIR / "archive (1)" / "postings.csv",
    RAW_DATA_DIR / "archive" / "linkedin_job_postings.csv",
    RAW_DATA_DIR / "archive" / "job_summary.csv",
)

RESUME_SOURCE_CANDIDATES = (RAW_DATA_DIR / "archive (3)" / "Resume" / "Resume.csv",)

JOB_COLUMN_ALIASES = {
    "job_id": ("job_id", "id", "jobid"),
    "title": ("title", "job_title", "position", "role"),
    "description": ("description", "job_description", "summary", "job_summary"),
    "skills": ("skills_desc", "skills", "job_skills"),
}

RESUME_COLUMN_ALIASES = {
    "resume_id": ("resume_id", "id", "candidate_id"),
    "category": ("category", "role", "resume_category"),
    "resume_text": ("resume_str", "resume", "text", "resume_html"),
}

CATEGORY_KEYWORDS = {
    "ACCOUNTANT": ("accountant", "accounting", "auditor", "bookkeeper", "tax accountant", "financial accountant"),
    "ADVOCATE": ("advocate", "attorney", "lawyer", "legal counsel", "paralegal", "legal advisor"),
    "AGRICULTURE": ("agriculture", "agronomist", "farm", "farmer", "horticulture", "crop", "livestock"),
    "APPAREL": ("apparel", "fashion", "garment", "textile", "merchandiser", "clothing", "retail buyer"),
    "ARTS": ("artist", "arts", "creative", "illustrator", "art director", "museum", "gallery"),
    "AUTOMOBILE": ("automotive", "automobile", "mechanic", "car technician", "service advisor", "auto technician"),
    "AVIATION": ("aviation", "pilot", "flight attendant", "airline", "aerospace", "aircraft", "aircrew"),
    "BANKING": ("banking", "banker", "bank manager", "loan officer", "credit analyst", "branch manager"),
    "BPO": ("bpo", "call center", "customer support", "customer service", "contact center", "telecaller"),
    "BUSINESS-DEVELOPMENT": (
        "business development",
        "partnership",
        "account executive",
        "sales development",
        "bdm",
        "alliances",
    ),
    "CHEF": ("chef", "cook", "culinary", "pastry chef", "commis", "kitchen manager"),
    "CONSTRUCTION": (
        "construction",
        "site engineer",
        "civil engineer",
        "project manager",
        "quantity surveyor",
        "foreman",
    ),
    "CONSULTANT": ("consultant", "advisor", "adviser", "strategy", "management consultant", "business consultant"),
    "DESIGNER": ("designer", "graphic designer", "ui designer", "ux designer", "product designer", "visual designer"),
    "DIGITAL-MEDIA": (
        "digital media",
        "content creator",
        "social media",
        "video editor",
        "digital marketing",
        "media planner",
    ),
    "ENGINEERING": (
        "engineer",
        "engineering",
        "mechanical engineer",
        "electrical engineer",
        "process engineer",
        "project engineer",
    ),
    "FINANCE": ("finance", "financial analyst", "fp&a", "controller", "investment analyst", "treasury", "risk analyst"),
    "FITNESS": ("fitness", "trainer", "personal trainer", "coach", "gym instructor", "wellness"),
    "HEALTHCARE": ("healthcare", "nurse", "doctor", "medical", "pharmacist", "therapist", "clinical"),
    "HR": ("hr", "human resources", "recruiter", "talent acquisition", "people operations", "hr manager"),
    "INFORMATION-TECHNOLOGY": (
        "information technology",
        "software engineer",
        "software developer",
        "developer",
        "programmer",
        "systems administrator",
        "system administrator",
        "devops",
        "data engineer",
        "data analyst",
        "solutions architect",
        "technical support",
        "it support",
    ),
    "PUBLIC-RELATIONS": ("public relations", "pr manager", "communications", "media relations", "brand communications"),
    "SALES": ("sales", "sales manager", "sales associate", "account manager", "sales executive", "inside sales"),
    "TEACHER": ("teacher", "educator", "instructor", "lecturer", "tutor", "faculty", "trainer"),
}


@dataclass(slots=True)
class PhaseOneResult:
    """Container for the cleaned corpora and pairwise relevance split."""

    jobs: pd.DataFrame
    resumes: pd.DataFrame
    pairs: pd.DataFrame
    train_pairs: pd.DataFrame
    eval_pairs: pd.DataFrame
    jobs_path: Path
    resumes_path: Path
    pairs_path: Path
    train_path: Path
    eval_path: Path


def _resolve_source_path(source: Path | str | None, candidates: Iterable[Path]) -> Path:
    if source is not None:
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file does not exist: {source_path}")
        return source_path

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError("No matching source file found in the configured raw data directory.")


def _matching_columns(columns: Iterable[str], aliases: dict[str, tuple[str, ...]]) -> dict[str, str]:
    normalized = {column.lower(): column for column in columns}
    resolved: dict[str, str] = {}

    for target_column, possible_names in aliases.items():
        for possible_name in possible_names:
            if possible_name.lower() in normalized:
                resolved[target_column] = normalized[possible_name.lower()]
                break

    return resolved


def _read_subset_csv(path: Path, aliases: dict[str, tuple[str, ...]]) -> pd.DataFrame:
    header = pd.read_csv(path, nrows=0)
    resolved_columns = _matching_columns(header.columns, aliases)
    if not resolved_columns:
        raise ValueError(f"No expected columns found in {path.name}.")

    frame = pd.read_csv(path, usecols=list(resolved_columns.values()), low_memory=False)
    rename_map = {source_name: target_name for target_name, source_name in resolved_columns.items()}
    return frame.rename(columns=rename_map)


def _ensure_clean_text_column(frame: pd.DataFrame, column_name: str) -> None:
    if column_name not in frame.columns:
        frame[column_name] = ""
    frame[column_name] = frame[column_name].astype("string").fillna("").str.strip()


def _normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = re.sub(r"[^0-9A-Za-z]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _combine_text(parts: Iterable[object]) -> str:
    cleaned_parts = [_normalize_text(part) for part in parts]
    return re.sub(r"\s+", " ", " ".join(part for part in cleaned_parts if part)).strip()


def _build_category_pattern(category: str) -> re.Pattern[str]:
    normalized_category = _normalize_text(category).upper().replace(" ", "-")
    keywords = CATEGORY_KEYWORDS.get(normalized_category, ())

    if not keywords:
        escaped_category = re.escape(_normalize_text(category))
        return re.compile(rf"(?:^|\s){escaped_category}(?:\s|$)")

    parts = []
    for keyword in keywords:
        normalized_keyword = re.escape(_normalize_text(keyword)).replace(r"\ ", r"\s+")
        parts.append(rf"(?:^|\s){normalized_keyword}(?:\s|$)")

    return re.compile("|".join(parts))


@lru_cache(maxsize=None)
def _cached_category_pattern(category: str) -> re.Pattern[str]:
    return _build_category_pattern(category)


def _normalize_category_value(category: object) -> str:
    normalized = _normalize_text(category)
    return normalized.upper().replace(" ", "-")


def load_jobs_csv(source: Path | str | None = None) -> pd.DataFrame:
    """Load and clean the jobs CSV into a standardized corpus."""

    source_path = _resolve_source_path(source, JOB_SOURCE_CANDIDATES)
    jobs = _read_subset_csv(source_path, JOB_COLUMN_ALIASES)

    if "title" not in jobs.columns:
        raise ValueError(f"The selected jobs CSV does not expose a title column: {source_path}")

    if "job_id" not in jobs.columns:
        jobs["job_id"] = range(1, len(jobs) + 1)

    jobs = jobs.rename(columns={"title": "job_title"})
    _ensure_clean_text_column(jobs, "job_title")
    _ensure_clean_text_column(jobs, "description")
    _ensure_clean_text_column(jobs, "skills")
    jobs["text"] = jobs.apply(lambda row: _combine_text([row["job_title"], row["description"], row["skills"]]), axis=1)
    jobs = jobs.loc[jobs["text"].ne("")].copy()
    jobs = jobs.drop_duplicates(subset=["job_id", "text"]).reset_index(drop=True)
    jobs["job_category"] = jobs["job_title"].map(_normalize_category_value)
    jobs["job_family"] = jobs["job_title"].map(derive_job_family)
    return jobs[["job_id", "job_title", "description", "skills", "text", "job_category", "job_family"]]


def load_resumes_csv(source: Path | str | None = None) -> pd.DataFrame:
    """Load and clean the resumes CSV into a standardized corpus."""

    source_path = _resolve_source_path(source, RESUME_SOURCE_CANDIDATES)
    resumes = _read_subset_csv(source_path, RESUME_COLUMN_ALIASES)

    if "category" not in resumes.columns or "resume_text" not in resumes.columns:
        raise ValueError(f"The selected resumes CSV must expose category and resume text columns: {source_path}")

    if "resume_id" not in resumes.columns:
        resumes["resume_id"] = range(1, len(resumes) + 1)

    resumes = resumes.rename(columns={"resume_text": "resume_text_raw"})
    _ensure_clean_text_column(resumes, "category")
    _ensure_clean_text_column(resumes, "resume_text_raw")
    resumes["text"] = resumes["resume_text_raw"].map(_normalize_text)
    resumes = resumes.loc[resumes["category"].ne("") & resumes["text"].ne("")].copy()
    resumes = resumes.drop_duplicates(subset=["resume_id", "text"]).reset_index(drop=True)
    resumes["resume_category"] = resumes["category"].map(_normalize_category_value)
    return resumes[["resume_id", "category", "resume_category", "resume_text_raw", "text"]]


def derive_job_family(job_title: str) -> str:
    """First-match-wins over `CATEGORY_KEYWORDS` against the lowercased title, else
    `"OTHER"`. Reuses the exact pattern machinery `label_relevance` already builds --
    see enhancements/05: `job_category` (the title uppercased) has 70,518 distinct
    values and cannot be a filter facet, so this coarse ~24-bucket family is the real
    facet instead.

    **Order-sensitive**: `CATEGORY_KEYWORDS` is a dict and iteration follows
    declaration order, so a title matching two categories' keywords is assigned to
    whichever is declared first. Changing the dict's order or contents changes this
    function's output; re-measure and append a new row to `measured-facts.md` if you do.
    """

    title = _normalize_text(job_title)
    if not title:
        return "OTHER"

    for category in CATEGORY_KEYWORDS:
        if _cached_category_pattern(category).search(title):
            return category

    return "OTHER"


def label_relevance(resume_category: str, job_title: str) -> int:
    """Return 1 when the job title matches the resume category proxy, otherwise 0."""

    category = _normalize_category_value(resume_category)
    title = _normalize_text(job_title)
    if not category or not title:
        return 0

    pattern = _cached_category_pattern(category)
    return int(bool(pattern.search(title)))


def _sample_records(frame: pd.DataFrame, count: int, random_state: int) -> pd.DataFrame:
    if len(frame) <= count:
        return frame.copy()
    return frame.sample(n=count, random_state=random_state).copy()


def build_relevance_pairs(
    resumes: pd.DataFrame,
    jobs: pd.DataFrame,
    negative_ratio: int = 3,
    positive_per_resume: int = 1,
    random_state: int = 42,
) -> pd.DataFrame:
    """Build a sampled pairwise relevance corpus from resumes and jobs."""

    rng = random_state
    job_titles = jobs[["job_id", "job_title", "text", "job_category"]].copy()
    job_titles["title_key"] = job_titles["job_title"].map(_normalize_text)

    category_to_jobs: dict[str, pd.DataFrame] = {}
    category_to_negatives: dict[str, pd.DataFrame] = {}
    unique_categories = resumes["resume_category"].dropna().unique().tolist()

    for category in unique_categories:
        pattern = _cached_category_pattern(category)
        matching_mask = job_titles["title_key"].str.contains(pattern, na=False)
        category_to_jobs[category] = job_titles.loc[matching_mask].copy()
        category_to_negatives[category] = job_titles.loc[~matching_mask].copy()

    pair_rows: list[dict[str, object]] = []

    for resume_index, resume_row in resumes.iterrows():
        category = resume_row["resume_category"]
        matching_jobs = category_to_jobs.get(category, pd.DataFrame()).copy()
        if matching_jobs.empty:
            continue

        positive_jobs = _sample_records(matching_jobs, positive_per_resume, rng + int(resume_index))
        negative_jobs = category_to_negatives.get(category, pd.DataFrame()).copy()
        negative_count = min(len(negative_jobs), max(1, len(positive_jobs)) * max(1, negative_ratio))
        negative_jobs = _sample_records(negative_jobs, negative_count, rng + int(resume_index) + 10_000)

        for job_row in positive_jobs.itertuples(index=False):
            pair_rows.append(
                {
                    "resume_id": resume_row["resume_id"],
                    "resume_category": resume_row["resume_category"],
                    "resume_text": resume_row["text"],
                    "job_id": job_row.job_id,
                    "job_title": job_row.job_title,
                    "job_text": job_row.text,
                    "relevance": 1,
                }
            )

        for job_row in negative_jobs.itertuples(index=False):
            pair_rows.append(
                {
                    "resume_id": resume_row["resume_id"],
                    "resume_category": resume_row["resume_category"],
                    "resume_text": resume_row["text"],
                    "job_id": job_row.job_id,
                    "job_title": job_row.job_title,
                    "job_text": job_row.text,
                    "relevance": 0,
                }
            )

    pairs = pd.DataFrame(pair_rows)
    if pairs.empty:
        return pairs

    pairs = pairs.drop_duplicates(subset=["resume_id", "job_id"]).reset_index(drop=True)
    return pairs[["resume_id", "resume_category", "resume_text", "job_id", "job_title", "job_text", "relevance"]]


def holdout_evaluation_split(
    labeled_pairs: pd.DataFrame,
    evaluation_fraction: float = 0.2,
    random_state: int = 42,
    group_column: str = "resume_id",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hold out an evaluation split while keeping grouped resumes together."""

    if labeled_pairs.empty:
        return labeled_pairs.copy(), labeled_pairs.copy()

    if group_column in labeled_pairs.columns and labeled_pairs[group_column].nunique() > 1:
        splitter = GroupShuffleSplit(n_splits=1, test_size=evaluation_fraction, random_state=random_state)
        train_indices, eval_indices = next(splitter.split(labeled_pairs, groups=labeled_pairs[group_column]))
        train_frame = labeled_pairs.iloc[train_indices].reset_index(drop=True)
        eval_frame = labeled_pairs.iloc[eval_indices].reset_index(drop=True)
        return train_frame, eval_frame

    stratify = labeled_pairs["relevance"] if labeled_pairs["relevance"].nunique() > 1 else None
    train_frame, eval_frame = train_test_split(
        labeled_pairs,
        test_size=evaluation_fraction,
        random_state=random_state,
        stratify=stratify,
    )
    return train_frame.reset_index(drop=True), eval_frame.reset_index(drop=True)


def _save_dataframe(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def prepare_phase_one_data(
    jobs_source: Path | str | None = None,
    resumes_source: Path | str | None = None,
    output_dir: Path | str | None = None,
    negative_ratio: int = 3,
    positive_per_resume: int = 1,
    evaluation_fraction: float = 0.2,
    random_state: int = 42,
) -> PhaseOneResult:
    """Run the phase 1 data preparation pipeline end to end."""

    output_path = Path(output_dir) if output_dir is not None else PROCESSED_DATA_DIR
    jobs = load_jobs_csv(jobs_source)
    resumes = load_resumes_csv(resumes_source)
    pairs = build_relevance_pairs(
        resumes=resumes,
        jobs=jobs,
        negative_ratio=negative_ratio,
        positive_per_resume=positive_per_resume,
        random_state=random_state,
    )
    train_pairs, eval_pairs = holdout_evaluation_split(
        pairs,
        evaluation_fraction=evaluation_fraction,
        random_state=random_state,
    )

    jobs_path = _save_dataframe(jobs, output_path / "jobs_clean.parquet")
    resumes_path = _save_dataframe(resumes, output_path / "resumes_clean.parquet")
    pairs_path = _save_dataframe(pairs, output_path / "relevance_pairs.parquet")
    train_path = _save_dataframe(train_pairs, output_path / "relevance_train.parquet")
    eval_path = _save_dataframe(eval_pairs, output_path / "relevance_eval.parquet")

    return PhaseOneResult(
        jobs=jobs,
        resumes=resumes,
        pairs=pairs,
        train_pairs=train_pairs,
        eval_pairs=eval_pairs,
        jobs_path=jobs_path,
        resumes_path=resumes_path,
        pairs_path=pairs_path,
        train_path=train_path,
        eval_path=eval_path,
    )
