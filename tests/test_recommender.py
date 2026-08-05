"""Roadmap generation: priority order, budget packing, and honest week counts."""

from __future__ import annotations

from ai.ats import score_resume
from ai.recommender import analyse_gaps, build_roadmap
from ai.resume_parser import parse_resume

THIN_RESUME = (
    b"Ravi Kumar\nravi@example.com\n+91 90000 11111\n"
    b"EDUCATION\nB.Tech CSE, 2022-2026\n"
    b"SKILLS\nPython, HTML, CSS\n"
    b"PROJECTS\n- Built a small calculator app in Python\n"
)


def _ats(role: str = "devops-engineer"):
    parsed = parse_resume(THIN_RESUME, "thin.txt")
    return score_resume(parsed, role, experience_level="fresher")


def test_missing_required_skills_are_ranked_critical():
    gaps = analyse_gaps(_ats())
    critical = [g for g in gaps if g["priority"] == "critical"]
    assert critical
    assert all(g["why"] for g in gaps), "every gap must explain itself to the candidate"


def test_interview_weaknesses_become_practice_items():
    summary = {
        "dimension_averages": {"relevance": 8.0, "depth": 7.0, "structure": 3.2,
                               "specificity": 4.5, "clarity": 7.5},
        "weakest_dimension": "structure",
    }
    gaps = analyse_gaps(_ats("full-stack-developer"), summary)
    drills = [g for g in gaps if g["kind"] == "interview-skill"]

    assert any("STAR" in g["skill"] for g in drills)
    assert all(g["priority"] in {"high", "medium"} for g in drills)
    # A dimension the candidate is already good at should not be scheduled.
    assert not any(g.get("dimension") == "relevance" for g in drills)


def test_no_week_is_overbooked():
    roadmap = build_roadmap(_ats(), weeks=8, hours_per_week=6)
    assert roadmap["weeks"]
    for week in roadmap["weeks"]:
        assert week["hours"] <= 6, f"week {week['week']} is over budget"


def test_a_large_item_is_split_across_weeks_not_dropped():
    """A 30-hour course must not vanish because it exceeds one week's budget."""
    roadmap = build_roadmap(_ats("ml-engineer"), weeks=12, hours_per_week=5)
    titles = [task["title"] for week in roadmap["weeks"] for task in week["tasks"]]
    assert any("part 1/" in title for title in titles)


def test_critical_work_is_scheduled_before_optional_work():
    roadmap = build_roadmap(_ats(), weeks=8, hours_per_week=8)
    priorities = [task["priority"] for week in roadmap["weeks"] for task in week["tasks"]]
    first_medium = next((i for i, p in enumerate(priorities) if p == "medium"), len(priorities))
    last_critical = max((i for i, p in enumerate(priorities) if p == "critical"), default=-1)
    assert last_critical < first_medium


def test_empty_trailing_weeks_are_trimmed():
    """Promising 24 weeks and filling 4 would make the plan look padded."""
    roadmap = build_roadmap(_ats("frontend-developer"), weeks=24, hours_per_week=20)
    assert roadmap["week_count"] == len(roadmap["weeks"])
    assert roadmap["weeks"][-1]["tasks"]


def test_a_candidate_with_no_gaps_still_gets_a_plan():
    parsed = parse_resume(
        b"SKILLS\nPython, SQL, REST APIs, Git, Database design, Testing, FastAPI, Docker\n"
        b"EDUCATION\nB.Tech\nEXPERIENCE\n- Built APIs\n",
        "full.txt")
    roadmap = build_roadmap(score_resume(parsed, "backend-developer"), weeks=4, hours_per_week=6)
    assert roadmap["weeks"]
    assert roadmap["coach_note"]


def test_week_themes_describe_what_is_actually_in_the_week():
    roadmap = build_roadmap(_ats(), weeks=8, hours_per_week=8)
    for week in roadmap["weeks"]:
        if week["tasks"]:
            assert any(skill in week["theme"] for skill in week["focus_skills"]) \
                   or week["theme"] == "Build week"


def test_every_task_carries_the_fields_the_ui_renders():
    roadmap = build_roadmap(_ats(), weeks=6, hours_per_week=8)
    for week in roadmap["weeks"]:
        assert week["outcome"]
        for task in week["tasks"]:
            assert {"skill", "title", "hours", "kind", "priority", "done"} <= set(task)
