"""Tests for `src/talentrank/explain.py` -- the lexical evidence layer, enhancements/04."""

from __future__ import annotations

from typing import Any

from src.talentrank.explain import _explain_normalize, build_resume_terms, explain_candidate


def _candidate(text: str, job_id: int = 1) -> dict[str, Any]:
    return {"job_id": job_id, "job_title": "Test Job", "text": text, "description": text}


def test_special_chars() -> None:
    """Regression test for the `\\b` trap: `\\bc++\\b` does not match what you'd
    expect since `\\b` is defined over `[A-Za-z0-9_]` and doesn't fire next to `+`,
    `#`, or `.`. `skills.py` uses lookarounds against an explicit boundary class
    instead."""

    resume = build_resume_terms("Experienced with C++, C#, .NET, and Node.js in production systems.")
    assert {"c++", "c#", ".net", "node.js"} <= resume.skills


def test_longest_alias_wins() -> None:
    resume = build_resume_terms("Strong background in machine learning and applied statistics.")
    assert "machine learning" in resume.skills
    assert "learning" not in resume.skills


def test_matched_and_missing_are_disjoint() -> None:
    resume = build_resume_terms("Registered nurse with ACLS certification and ICU experience.")
    candidate = _candidate("Seeking a registered nurse with ACLS and BLS certification for our ICU.")

    explanation = explain_candidate(resume, candidate, idf={})

    assert set(explanation.matched_skills).isdisjoint(explanation.missing_skills)
    assert "bls" in explanation.missing_skills  # resume never mentions BLS


def test_overlap_score_bounds() -> None:
    resume = build_resume_terms("Sales associate experienced in cold calling and lead generation.")

    no_skills_candidate = _candidate("General office responsibilities and daily operations as assigned.")
    explanation = explain_candidate(resume, no_skills_candidate, idf={})
    assert 0.0 <= explanation.overlap_score <= 1.0
    assert explanation.matched_skills == []

    matching_candidate = _candidate("Sales associate skilled in cold calling, lead generation, and CRM.")
    explanation = explain_candidate(resume, matching_candidate, idf={})
    assert 0.0 <= explanation.overlap_score <= 1.0
    assert explanation.matched_skills != []


def test_empty_resume() -> None:
    resume = build_resume_terms("")
    candidate = _candidate("Registered nurse needed, ACLS certified, ICU experience required.")

    explanation = explain_candidate(resume, candidate, idf={})

    assert explanation.matched_skills == []
    assert explanation.matched_terms == []
    assert 0.0 <= explanation.overlap_score <= 1.0


def test_normalizer_preserves_symbols() -> None:
    normalized = _explain_normalize("Node.JS / C++")
    assert normalized == "node.js / c++"
    assert "." in normalized
    assert "+" in normalized
    assert "/" in normalized


def test_cross_domain_coverage() -> None:
    """Catches a tech-only lexicon: a nurse resume against a nursing description
    must produce non-empty matched_skills, not just software terms."""

    nurse_resume = build_resume_terms(
        "Registered nurse, 6 years ICU, ACLS and BLS certified, EMR charting, patient triage, wound care"
    )
    nursing_job = _candidate(
        "Seeking a registered nurse for our ICU with ACLS/BLS certification, EMR charting, "
        "and patient triage experience."
    )

    explanation = explain_candidate(nurse_resume, nursing_job, idf={})

    assert explanation.matched_skills != []
