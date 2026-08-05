"""
Skill-gap analysis and the personalised learning roadmap.

WHAT MAKES A ROADMAP USEFUL
---------------------------
Not a list of topics - a *schedule that fits*. Every roadmap this module
produces is packed against a real weekly budget (default 8 hours), so the
candidate gets "week 3: 7 hours, these two things" instead of "learn system
design". A plan that cannot fit into a student's week is a plan that gets
abandoned in week one.

PRIORITY ORDER
--------------
1. Missing must-have skills for the target role  (you get filtered out without these)
2. Interview weaknesses measured in mock rounds  (you get rejected in the room)
3. Missing good-to-have skills                   (these are the differentiators)

Interview weaknesses come second, not last, because a candidate who has every
skill but cannot structure an answer fails at exactly the same rate as one who
is missing Docker - and only this product can see that.
"""

from __future__ import annotations

from typing import Any

from .llm import get_llm
from .skills_db import resources_for, role_or_default

DEFAULT_WEEKS = 8
DEFAULT_HOURS_PER_WEEK = 8

# Interview dimensions -> what to actually practise.
DIMENSION_DRILLS: dict[str, dict[str, Any]] = {
    "relevance": {
        "title": "Answer the question that was asked",
        "hours": 2,
        "tasks": [
            "Before answering, repeat the question in your own words in one sentence.",
            "Record 5 answers; for each, write down the question's actual ask and check you hit it.",
        ],
    },
    "depth": {
        "title": "Go one level deeper than the definition",
        "hours": 3,
        "tasks": [
            "For your top 5 resume skills, write the 'why does it work that way' answer, not the 'what is it'.",
            "Practise the follow-up: after every answer, ask yourself 'and why?' twice more.",
        ],
    },
    "structure": {
        "title": "Structure every answer (STAR)",
        "hours": 3,
        "tasks": [
            "Write out 6 STAR stories from your projects: Situation, Task, Action, Result - one page each.",
            "Rehearse each in 90 seconds out loud. Time yourself.",
        ],
    },
    "specificity": {
        "title": "Put numbers and names in your answers",
        "hours": 2,
        "tasks": [
            "Go through your resume and attach a metric to every bullet that lacks one.",
            "For each project, memorise 3 concrete numbers (users, latency, dataset size, accuracy).",
        ],
    },
    "clarity": {
        "title": "Cut fillers and rambling",
        "hours": 2,
        "tasks": [
            "Record 5 answers, transcribe them, and count 'um', 'like', 'basically'.",
            "Practise pausing instead of filling. Target under 2% filler words.",
        ],
    },
}

def _theme_for(week: dict[str, Any]) -> str:
    """Name the week after what is actually in it.

    An earlier version used a fixed list of nice-sounding themes ("Week 4:
    Interview delivery") which regularly disagreed with the tasks scheduled
    underneath it. A label that contradicts the content is worse than no label.
    """
    if not week["tasks"]:
        return "Buffer week"
    skills = week["focus_skills"]
    kinds = {task["kind"] for task in week["tasks"]}
    if len(skills) == 1:
        return f"Focus: {skills[0]}"
    if kinds == {"project"}:
        return "Build week"
    return "Focus: " + " + ".join(skills[:2])


def analyse_gaps(
    ats_result: dict[str, Any],
    interview_summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rank what this candidate should learn, and say why for each item."""
    gaps: list[dict[str, Any]] = []

    for skill in ats_result.get("missing_must_have") or []:
        gaps.append({
            "skill": skill,
            "priority": "critical",
            "kind": "skill",
            "why": f"{skill} is a stated requirement for {ats_result.get('role_title', 'this role')}. "
                   "Resumes without it are filtered out before a human reads them.",
            "resources": resources_for(skill),
        })

    if interview_summary:
        averages = interview_summary.get("dimension_averages") or {}
        for dimension, average in sorted(averages.items(), key=lambda kv: kv[1]):
            if average >= 6.5 or dimension not in DIMENSION_DRILLS:
                continue
            drill = DIMENSION_DRILLS[dimension]
            gaps.append({
                "skill": drill["title"],
                "priority": "high" if average < 5 else "medium",
                "kind": "interview-skill",
                "dimension": dimension,
                "why": f"Your mock interviews averaged {average}/10 on {dimension}. "
                       "This costs you offers even when the technical answer is right.",
                "resources": [{"title": task, "url": "", "kind": "practice",
                               "hours": max(1, drill["hours"] // len(drill["tasks"]))}
                              for task in drill["tasks"]],
            })

    for skill in (ats_result.get("missing_good_to_have") or [])[:4]:
        gaps.append({
            "skill": skill,
            "priority": "medium",
            "kind": "skill",
            "why": f"{skill} is listed as preferred. It is what separates you from "
                   "candidates who only meet the minimum.",
            "resources": resources_for(skill),
        })

    return gaps


def build_roadmap(
    ats_result: dict[str, Any],
    interview_summary: dict[str, Any] | None = None,
    *,
    weeks: int = DEFAULT_WEEKS,
    hours_per_week: int = DEFAULT_HOURS_PER_WEEK,
    role_key: str | None = None,
) -> dict[str, Any]:
    """Produce a week-by-week plan that fits the candidate's actual budget."""
    role_key, role = role_or_default(role_key or ats_result.get("role_key"))
    weeks = max(2, min(24, weeks))
    hours_per_week = max(2, min(40, hours_per_week))

    gaps = analyse_gaps(ats_result, interview_summary)
    if not gaps:
        gaps = _maintenance_plan(role)

    # Flatten every gap into schedulable items, keeping priority order.
    backlog: list[dict[str, Any]] = []
    for gap in gaps:
        for resource in gap["resources"]:
            backlog.append({
                "skill": gap["skill"],
                "priority": gap["priority"],
                "title": resource["title"],
                "url": resource.get("url", ""),
                "kind": resource.get("kind", "reading"),
                "hours": int(resource.get("hours", 4)),
            })

    plan = _pack_weeks(backlog, weeks, hours_per_week)

    total_hours = sum(week["hours"] for week in plan)
    scheduled_skills = {task["skill"] for week in plan for task in week["tasks"]}
    unscheduled = [g["skill"] for g in gaps if g["skill"] not in scheduled_skills]

    roadmap = {
        "role_key": role_key,
        "role_title": role["title"],
        "weeks": plan,
        "week_count": len(plan),
        "hours_per_week": hours_per_week,
        "total_hours": total_hours,
        "gaps": gaps,
        "critical_count": sum(1 for g in gaps if g["priority"] == "critical"),
        "did_not_fit": unscheduled,
        # Computed AFTER packing so the note quotes the plan that actually
        # exists. Quoting the requested 8 weeks next to a rendered 3-week plan
        # makes the whole page look like it is guessing.
        "coach_note": _coach_note(
            ats_result, interview_summary, gaps, len(plan), hours_per_week, total_hours),
    }
    return roadmap


# --------------------------------------------------------------------------- #
# Scheduling
# --------------------------------------------------------------------------- #

PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _pack_weeks(
    backlog: list[dict[str, Any]],
    weeks: int,
    hours_per_week: int,
) -> list[dict[str, Any]]:
    """First-fit packing by priority.

    An item bigger than a whole week (a 30-hour course) is split across
    consecutive weeks rather than dropped, because dropping the most important
    item for being large is exactly the wrong behaviour.
    """
    ordered = sorted(backlog, key=lambda item: PRIORITY_RANK.get(item["priority"], 3))
    plan: list[dict[str, Any]] = [
        {"week": index + 1, "theme": "", "tasks": [], "hours": 0,
         "focus_skills": [], "outcome": ""}
        for index in range(weeks)
    ]

    week_index = 0
    for item in ordered:
        remaining = item["hours"]
        part = 1
        parts_needed = -(-remaining // hours_per_week)  # ceil
        while remaining > 0 and week_index < weeks:
            week = plan[week_index]
            space = hours_per_week - week["hours"]
            if space <= 0:
                week_index += 1
                continue
            chunk = min(space, remaining)
            title = item["title"]
            if parts_needed > 1:
                title = f"{title} (part {part}/{parts_needed})"
            week["tasks"].append({
                "skill": item["skill"], "title": title, "url": item["url"],
                "kind": item["kind"], "hours": chunk, "priority": item["priority"],
                "done": False,
            })
            week["hours"] += chunk
            remaining -= chunk
            part += 1
            if week["hours"] >= hours_per_week:
                week_index += 1
        if week_index >= weeks:
            break

    for week in plan:
        week["focus_skills"] = _dedupe([task["skill"] for task in week["tasks"]])
        week["theme"] = _theme_for(week)
        week["outcome"] = _outcome_for(week)

    # Drop trailing empty weeks - promising 8 weeks and filling 5 is dishonest.
    while plan and not plan[-1]["tasks"]:
        plan.pop()
    return plan


def _outcome_for(week: dict[str, Any]) -> str:
    """A concrete, checkable finish line for the week.

    The sentence has to fit what is actually scheduled. Interview drills are
    named as instructions ("Structure every answer (STAR)"), so dropping them
    into "you can answer a question on ___" produces nonsense - they get their
    own phrasing.
    """
    if not week["tasks"]:
        return "Buffer week - revise and take a full mock interview."

    projects = [t for t in week["tasks"] if t["kind"] == "project"]
    if projects:
        title = projects[0]["title"].split("(part")[0].strip()
        return f"By Sunday: {title} is done and pushed to GitHub."

    # Interview drills are the entries whose "skill" is a whole instruction
    # rather than a technology name, which is exactly what a space in it means.
    drills = [t for t in week["tasks"] if t["kind"] == "practice" and " " in t["skill"]]
    if drills and len(drills) >= len(week["tasks"]) / 2:
        return ("By Sunday: record a full mock interview and check that this week's "
                "drill actually shows up in how you answer.")

    skills = ", ".join(week["focus_skills"][:2])
    return f"By Sunday: you can answer an interview question on {skills} without notes."


def _maintenance_plan(role: dict) -> list[dict[str, Any]]:
    """Nothing is missing - keep the candidate sharp instead of saying 'nice work'."""
    return [{
        "skill": skill,
        "priority": "medium",
        "kind": "skill",
        "why": f"No gaps were detected for {role['title']}. Deepen {skill} so you can "
               "handle the follow-up questions, not just the first one.",
        "resources": resources_for(skill),
    } for skill in role["must_have"][:3]]


# --------------------------------------------------------------------------- #
# Coach note (LLM-optional)
# --------------------------------------------------------------------------- #

COACH_SYSTEM = (
    "You are a career coach writing to a student. Be direct, warm and specific. "
    "No motivational filler. Reference their actual gaps and the time they have."
)


def _coach_note(
    ats_result: dict[str, Any],
    interview_summary: dict[str, Any] | None,
    gaps: list[dict[str, Any]],
    weeks: int,
    hours_per_week: int,
    total_hours: int,
) -> str:
    critical = [g["skill"] for g in gaps if g["priority"] == "critical"]
    fallback = (
        f"This plan is {total_hours} hours of work across {weeks} week"
        f"{'s' if weeks != 1 else ''}, at {hours_per_week} hours a week. "
        + (
            f"Spend the first block on {', '.join(critical[:2])}; without those, "
            "your resume does not reach a human. "
            if critical else
            "Your resume already covers the required skills, so the leverage is in delivery. "
        )
        + (
            f"Your weakest interview dimension is "
            f"{interview_summary.get('weakest_dimension')} - drill that every week, not just once."
            if interview_summary and interview_summary.get("weakest_dimension")
            else "Run a mock interview at the end of every week and track the score."
        )
    )

    llm = get_llm()
    if not llm.available:
        return fallback

    prompt = (
        f"ATS score: {ats_result.get('score')}/100 for {ats_result.get('role_title')}.\n"
        f"Missing required skills: {', '.join(ats_result.get('missing_must_have') or []) or 'none'}.\n"
        f"Mock interview: {interview_summary.get('headline') if interview_summary else 'not taken yet'}.\n"
        f"The plan we built: {total_hours} hours over {weeks} weeks at "
        f"{hours_per_week} hours a week.\n\n"
        "Write a 3-4 sentence note telling this student what to do first and what to "
        'ignore for now. Return JSON: {"note": str}'
    )
    data = llm.complete_json(COACH_SYSTEM, prompt, fallback={"note": fallback}, max_tokens=500)
    note = data.get("note") if isinstance(data, dict) else None
    return str(note) if note else fallback


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
