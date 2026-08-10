"""Lexical evidence layer for TalentRank matches.

The cross-encoder score is not interpretable on its own, so this module builds a
separate, honest layer next to it: which skills the resume and job share, which the
job wants that the resume lacks, and which shared terms are rare enough (by corpus
IDF) to be worth highlighting. Ranking stays purely the cross-encoder's -- see
enhancements/04's Do-NOT section. `overlap_score` here is evidence shown beside the
ranking, never an input to it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from src.talentrank.config import get_settings
from src.talentrank.schemas import Explanation, MatchedTerm
from src.talentrank.skills import extract_skills

# Preserves `+ # . / -` -- unlike `data._normalize_text`, which strips everything
# non-alphanumeric and would destroy exactly the tokens (`c++`, `c#`, `.net`,
# `node.js`) that `skills.py`'s matcher depends on seeing intact.
_SYMBOL_SAFE_STRIP = re.compile(r"[^a-z0-9+#./\-\s]")
_WHITESPACE = re.compile(r"\s+")
_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#./-]*")

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "at",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "this",
        "that",
        "these",
        "those",
        "as",
        "it",
        "its",
        "we",
        "you",
        "your",
        "our",
        "their",
        "his",
        "her",
        "he",
        "she",
        "they",
        "i",
        "will",
        "would",
        "can",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "not",
        "no",
        "so",
        "if",
        "then",
        "than",
        "also",
        "into",
        "about",
        "over",
        "under",
        "after",
        "before",
        "between",
        "during",
        "through",
        "up",
        "down",
        "out",
        "all",
        "any",
        "each",
        "other",
        "more",
        "most",
        "some",
        "such",
        "only",
        "own",
        "same",
    }
)


def _explain_normalize(text: str) -> str:
    """Lowercase and collapse whitespace while preserving `+ # . / -`.

    `data._normalize_text` cannot be reused here: it strips everything
    non-alphanumeric, which would destroy `c++`, `c#`, `.net`, and `node.js` before
    either the tokenizer or `skills.extract_skills` ever saw them.
    """

    lowered = text.lower()
    stripped = _SYMBOL_SAFE_STRIP.sub(" ", lowered)
    return _WHITESPACE.sub(" ", stripped).strip()


def _tokenize(normalized_text: str) -> Counter[str]:
    tokens = [token for token in _TOKEN_PATTERN.findall(normalized_text) if len(token) > 1 and token not in _STOPWORDS]
    return Counter(tokens)


@dataclass(slots=True)
class ResumeTerms:
    """Built once per request (not per candidate) -- see `build_resume_terms`."""

    skills: frozenset[str]
    tokens: Counter[str] = field(default_factory=Counter)
    raw: str = ""


def build_resume_terms(resume_text: str) -> ResumeTerms:
    """Extract skills and token frequencies from a resume, once per request."""

    settings = get_settings()
    capped = str(resume_text)[: settings.rerank_text_max_chars]
    return ResumeTerms(
        skills=extract_skills(capped),
        tokens=_tokenize(_explain_normalize(capped)),
        raw=capped,
    )


def _candidate_text(candidate: dict[str, Any]) -> str:
    text = candidate.get("job_text") or candidate.get("text") or candidate.get("description") or ""
    settings = get_settings()
    return str(text)[: settings.rerank_text_max_chars]


def explain_candidate(
    resume_terms: ResumeTerms,
    candidate: dict[str, Any],
    idf: Mapping[str, float],
) -> Explanation:
    """Build the lexical evidence layer for one already-ranked, already-sliced
    candidate. Runs on the final `top_n` results, never on the full shortlist -- see
    enhancements/04, "Where it runs"."""

    settings = get_settings()
    job_text = _candidate_text(candidate)
    job_skills = extract_skills(job_text)

    matched_skills = sorted(resume_terms.skills & job_skills)
    missing = job_skills - resume_terms.skills
    missing_skills = sorted(missing, key=lambda term: idf.get(term, 0.0), reverse=True)
    overlap_score = len(matched_skills) / max(1, len(job_skills))

    job_tokens = _tokenize(_explain_normalize(job_text))
    shared_tokens = set(resume_terms.tokens) & set(job_tokens)
    ranked_terms = sorted(
        (term for term in shared_tokens if idf.get(term, 0.0) >= settings.explain_min_idf),
        key=lambda term: idf.get(term, 0.0),
        reverse=True,
    )[: settings.explain_max_terms]
    matched_terms = [MatchedTerm(term=term, weight=idf.get(term, 0.0)) for term in ranked_terms]

    return Explanation(
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        matched_terms=matched_terms,
        overlap_score=overlap_score,
    )
