"""ATS scoring: determinism, weighting, and that the advice matches the score."""

from __future__ import annotations

import pytest

from ai.ats import WEIGHTS, score_resume
from ai.resume_parser import parse_resume


@pytest.fixture
def parsed(sample_resume_bytes):
    return parse_resume(sample_resume_bytes, "sample_resume.txt")


def test_same_input_always_scores_the_same(parsed):
    """The headline promise of a rule-based scorer. If this ever fails, the
    number on the dashboard has stopped meaning anything."""
    first = score_resume(parsed, "full-stack-developer")
    second = score_resume(parsed, "full-stack-developer")
    assert first["score"] == second["score"]
    assert first["breakdown"] == second["breakdown"]


def test_a_strong_matching_resume_scores_well(parsed):
    result = score_resume(parsed, "full-stack-developer", experience_level="fresher")
    assert result["score"] >= 75
    assert result["missing_must_have"] == []


def test_the_same_resume_scores_lower_against_an_unrelated_role(parsed):
    full_stack = score_resume(parsed, "full-stack-developer")
    devops = score_resume(parsed, "devops-engineer")
    assert devops["score"] < full_stack["score"]
    assert devops["missing_must_have"]


def test_missing_required_skills_are_named_in_the_advice(parsed):
    result = score_resume(parsed, "devops-engineer")
    missing = result["missing_must_have"]
    assert missing
    advice = " ".join(result["suggestions"])
    assert any(skill in advice for skill in missing)


def test_weights_sum_to_one_hundred():
    assert sum(WEIGHTS.values()) == 100


def test_job_description_points_are_redistributed_when_no_jd_is_given(parsed):
    without = score_resume(parsed, "full-stack-developer")
    with_jd = score_resume(parsed, "full-stack-developer", job_description="React and Node.js.")

    skills_without = next(b for b in without["breakdown"] if b["key"] == "skills")
    skills_with = next(b for b in with_jd["breakdown"] if b["key"] == "skills")

    assert skills_without["max"] == WEIGHTS["skills"] + WEIGHTS["job_description"]
    assert skills_with["max"] == WEIGHTS["skills"]
    assert not any(b["key"] == "job_description" for b in without["breakdown"])


def test_job_description_keywords_are_matched_and_missing_ones_reported(parsed):
    jd = ("Full Stack Developer. React, TypeScript, Node.js, PostgreSQL required. "
          "Kubernetes and GraphQL experience is a strong plus. Kubernetes clusters, "
          "GraphQL schemas.")
    result = score_resume(parsed, "full-stack-developer", job_description=jd)
    jd_part = next(b for b in result["breakdown"] if b["key"] == "job_description")

    assert "react" in jd_part["matched"]
    assert "kubernetes" in jd_part["missing"]


def test_an_unreadable_resume_scores_badly_and_says_why():
    parsed = parse_resume(b"Ravi\nsome words\n", "resume.txt")
    result = score_resume(parsed, "backend-developer")
    assert result["score"] < 45
    assert result["grade"] in {"D", "F"}
    assert result["suggestions"]


def test_impact_scoring_separates_duties_from_results():
    duties = parse_resume(
        b"SKILLS\nPython SQL\nEXPERIENCE\n- Responsible for the backend\n- Worked on APIs\n",
        "a.txt")
    results = parse_resume(
        b"SKILLS\nPython SQL\nEXPERIENCE\n- Built 12 APIs, cutting latency from 480ms to 120ms\n"
        b"- Automated reports, saving 6 hours a week\n- Raised coverage from 31% to 68%\n",
        "b.txt")

    duties_impact = next(b for b in score_resume(duties, "backend-developer")["breakdown"]
                         if b["key"] == "impact")
    results_impact = next(b for b in score_resume(results, "backend-developer")["breakdown"]
                          if b["key"] == "impact")
    assert results_impact["score"] > duties_impact["score"] + 3


def test_unknown_role_falls_back_instead_of_raising(parsed):
    result = score_resume(parsed, "wizard-of-devops")
    assert result["role_key"] == "full-stack-developer"


def test_score_never_leaves_zero_to_one_hundred(parsed):
    for role in ("frontend-developer", "ml-engineer", "qa-engineer", "sde-fresher"):
        for level in ("fresher", "senior"):
            result = score_resume(parsed, role, experience_level=level)
            assert 0 <= result["score"] <= 100
