"""Question generation and answer evaluation, both on the offline engines."""

from __future__ import annotations

import pytest

from ai.evaluator import evaluate_answer, evaluate_code, summarise_interview
from ai.question_gen import generate_coding_problems, generate_questions
from ai.resume_parser import parse_resume


@pytest.fixture
def parsed(sample_resume_bytes):
    return parse_resume(sample_resume_bytes, "sample_resume.txt")


# --------------------------------------------------------------------------- #
# Question generation
# --------------------------------------------------------------------------- #


def test_returns_the_requested_number_of_unique_questions(parsed):
    questions = generate_questions(parsed, "full-stack-developer", count=8, seed=1)
    assert len(questions) == 8
    assert len({q["text"] for q in questions}) == 8


def test_every_question_has_the_fields_the_ui_and_scorer_need(parsed):
    for question in generate_questions(parsed, "backend-developer", count=6, seed=2):
        assert question["text"]
        assert question["category"] in {"technical", "behavioral", "situational", "resume"}
        assert question["difficulty"] in {"easy", "medium", "hard"}
        assert isinstance(question["expected_points"], list)
        assert question["time_limit_sec"] > 0


def test_the_same_seed_gives_the_same_interview(parsed):
    """A candidate who refreshes mid-interview must not get new questions."""
    first = generate_questions(parsed, "backend-developer", count=6, seed=42)
    second = generate_questions(parsed, "backend-developer", count=6, seed=42)
    assert [q["text"] for q in first] == [q["text"] for q in second]


def test_company_profile_changes_the_question_mix(parsed):
    service = generate_questions(parsed, "sde-fresher", "service-company", count=10, seed=5)
    startup = generate_questions(parsed, "sde-fresher", "product-startup", count=10, seed=5)

    def share(questions, category):
        return sum(1 for q in questions if q["category"] == category) / len(questions)

    assert share(service, "behavioral") >= share(startup, "behavioral")
    assert share(startup, "resume") >= share(service, "resume")


def test_questions_can_be_generated_without_a_resume():
    questions = generate_questions(None, "data-analyst", count=5, seed=3)
    assert len(questions) == 5
    assert all(q["category"] != "resume" for q in questions)


def test_resume_questions_quote_whole_bullets_not_fragments(parsed):
    """Regression: wrapped resume lines used to be quoted mid-sentence."""
    questions = generate_questions(parsed, "full-stack-developer", "product-startup",
                                   count=10, seed=7)
    for question in questions:
        if '"' not in question["text"]:
            continue
        quoted = question["text"].split('"')[1]
        assert not quoted[0].islower(), f"quote starts mid-sentence: {quoted!r}"


def test_coding_problems_are_relevant_to_the_role():
    problems = generate_coding_problems("data-analyst", count=2, seed=1)
    assert len(problems) == 2
    for problem in problems:
        assert problem["category"] == "coding"
        assert problem["starter_code"]
        assert problem["expected_points"]


# --------------------------------------------------------------------------- #
# Answer evaluation
# --------------------------------------------------------------------------- #

QUESTION = {
    "text": "A query that used to take 100ms now takes 8 seconds. How do you find out why?",
    "category": "technical",
    "expected_points": ["EXPLAIN / query plan", "missing or unusable index",
                        "data growth and statistics", "N+1 from the app"],
}

GOOD_ANSWER = (
    "First I would reproduce it and run EXPLAIN ANALYZE to get the actual query plan. "
    "Usually the plan has flipped from an index scan to a sequential scan, either because "
    "the table grew and the statistics are stale, or because someone changed the WHERE "
    "clause so the existing index is no longer usable. I would check whether the data "
    "volume changed, run ANALYZE to refresh statistics, and look at whether the "
    "application is issuing an N+1 pattern. When I hit this at my internship the fix was "
    "a composite index on tenant_id and created_at, which took it from 480 milliseconds "
    "back to 120 milliseconds."
)

WEAK_ANSWER = "Um, I would like, basically check the database and see, you know, what is wrong."


def test_a_strong_answer_outscores_a_weak_one_on_every_dimension():
    strong = evaluate_answer(QUESTION, GOOD_ANSWER, duration_sec=55)
    weak = evaluate_answer(QUESTION, WEAK_ANSWER, duration_sec=8)

    assert strong["overall"] > weak["overall"] + 25
    for dimension in ("relevance", "depth", "specificity"):
        assert strong["scores"][dimension] > weak["scores"][dimension]


def test_scores_stay_inside_the_rubric_range():
    for answer in (GOOD_ANSWER, WEAK_ANSWER, "x " * 800):
        result = evaluate_answer(QUESTION, answer)
        assert 0 <= result["overall"] <= 100
        assert all(0 <= score <= 10 for score in result["scores"].values())


def test_filler_words_are_counted_and_cost_clarity():
    result = evaluate_answer(QUESTION, WEAK_ANSWER, duration_sec=8)
    assert result["metrics"]["filler_count"] >= 3
    assert result["scores"]["clarity"] < 7


def test_speaking_pace_is_measured_when_a_duration_is_given():
    rushed = evaluate_answer(QUESTION, GOOD_ANSWER, duration_sec=15)
    steady = evaluate_answer(QUESTION, GOOD_ANSWER, duration_sec=55)
    assert rushed["metrics"]["pace"] == "too fast"
    assert steady["metrics"]["pace"] == "good"


def test_spoken_numbers_count_as_quantified_claims():
    """'480 milliseconds' is how people speak; '480ms' is how they write."""
    result = evaluate_answer(QUESTION, GOOD_ANSWER, duration_sec=55)
    assert result["metrics"]["quantified_claims"] >= 2


def test_an_empty_answer_scores_zero_and_says_something_useful():
    result = evaluate_answer(QUESTION, "")
    assert result["overall"] == 0
    assert result["improvements"]


def test_missed_expected_points_are_reported_back():
    result = evaluate_answer(QUESTION, "I would add an index.")
    assert result["missed_points"]


def test_behavioural_answers_are_judged_on_structure():
    question = {"text": "Tell me about a project you are proud of.", "category": "behavioral",
                "expected_points": ["situation and goal", "what YOU did", "the outcome"]}
    star = ("At the time our clinic app had no booking flow. My job was to ship one in three "
            "weeks. I designed the schema, built the FastAPI endpoints and wrote the tests. "
            "As a result we handled 400 bookings a month across three pilot clinics.")
    rambling = ("So the project was a clinic app and it had lots of parts and we used React "
                "and it was quite interesting and there was a database as well.")

    assert (evaluate_answer(question, star)["scores"]["structure"]
            > evaluate_answer(question, rambling)["scores"]["structure"])


# --------------------------------------------------------------------------- #
# Code review + interview summary
# --------------------------------------------------------------------------- #


def test_code_review_never_executes_the_submission():
    problem = generate_coding_problems("sde-fresher", count=1, seed=1)[0]
    malicious = "import os\ndef solve():\n    os.system('echo pwned')\n"
    result = evaluate_code(problem, malicious)
    assert "not executed" in result["note"]
    assert result["overall"] >= 0


def test_code_review_flags_an_unfinished_stub():
    problem = generate_coding_problems("sde-fresher", count=1, seed=1)[0]
    result = evaluate_code(problem, problem["starter_code"])
    stub_check = next(c for c in result["static_checks"] if c["name"] == "Not a stub")
    assert stub_check["passed"] is False


def test_code_review_reports_a_syntax_error():
    problem = generate_coding_problems("sde-fresher", count=1, seed=1)[0]
    result = evaluate_code(problem, "def broken(:\n    return 1")
    parses = next(c for c in result["static_checks"] if c["name"] == "Parses")
    assert parses["passed"] is False


def test_interview_summary_averages_each_dimension():
    questions = [{"category": "technical"}, {"category": "behavioral"}]
    evaluations = [
        evaluate_answer(QUESTION, GOOD_ANSWER, duration_sec=55),
        evaluate_answer(QUESTION, WEAK_ANSWER, duration_sec=8),
    ]
    summary = summarise_interview(evaluations, questions, "Backend Developer")

    assert summary["answered"] == 2
    assert set(summary["dimension_averages"]) == {
        "relevance", "depth", "structure", "specificity", "clarity"}
    assert summary["strongest_dimension"] in summary["dimension_averages"]
    assert 0 <= summary["overall"] <= 100


def test_summary_of_an_interview_with_no_answers_is_not_a_crash():
    summary = summarise_interview([], [{"category": "technical"}], "Backend Developer")
    assert summary["overall"] == 0
    assert summary["answered"] == 0
