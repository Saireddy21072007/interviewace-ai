"""
ATS scoring - how a real applicant-tracking system would read this resume.

THE SCORE IS A CONTRACT, NOT AN OPINION
---------------------------------------
Five sub-scores, fixed weights, all arithmetic. Same resume + same role always
gives the same number, and every point is traceable to a rule the candidate can
read. The UI shows the breakdown, not just the total, because "72/100" is
useless feedback and "you lost 12 points because you have no quantified results"
is actionable.

    Skill match       40   do you have the skills the role asks for
    Job-description   15   do you use the words in THIS posting
    Parseability      15   can software read the file at all
    Impact            15   do bullets show results, not duties
    Fit               15   experience + education line up with the level

If no job description is supplied, its 15 points are redistributed to skill
match (which becomes 55), so a resume is never penalised for something the
candidate did not provide.
"""

from __future__ import annotations

import re
from typing import Any

from .llm import get_llm
from .skills_db import ALIAS_TO_SKILL, SOFT_SKILLS, role_or_default

WEIGHTS = {
    "skills": 40,
    "job_description": 15,
    "parseability": 15,
    "impact": 15,
    "fit": 15,
}

# What "enough" experience looks like per level, in years.
LEVEL_EXPECTATIONS = {
    "fresher": 0.0,
    "junior": 1.0,
    "mid": 3.0,
    "senior": 6.0,
}

STOPWORDS = {
    "the", "and", "for", "with", "you", "our", "will", "are", "have", "this",
    "that", "from", "your", "who", "all", "any", "can", "not", "but", "has",
    "was", "were", "their", "they", "them", "its", "into", "about", "more",
    "such", "than", "then", "there", "these", "those", "each", "other", "some",
    "work", "team", "role", "job", "years", "year", "experience", "ability",
    "strong", "good", "excellent", "knowledge", "skills", "required", "must",
    "plus", "preferred", "responsibilities", "requirements", "candidate",
    "candidates", "should", "would", "using", "help", "make", "well", "like",
}


def score_resume(
    parsed: dict[str, Any],
    role_key: str | None = None,
    job_description: str | None = None,
    experience_level: str = "fresher",
) -> dict[str, Any]:
    """Score a parsed resume against a role. Pure function, no I/O."""
    role_key, role = role_or_default(role_key)
    have = set(parsed.get("skill_list") or [])
    jd = (job_description or "").strip()

    weights = dict(WEIGHTS)
    if not jd:
        weights["skills"] += weights.pop("job_description")

    breakdown: list[dict[str, Any]] = []

    skills_part = _score_skills(have, role, weights["skills"])
    breakdown.append(skills_part)

    if jd:
        breakdown.append(_score_job_description(parsed, jd, weights["job_description"]))

    breakdown.append(_score_parseability(parsed, weights["parseability"]))
    breakdown.append(_score_impact(parsed, weights["impact"]))
    breakdown.append(_score_fit(parsed, experience_level, weights["fit"]))

    total = round(sum(part["score"] for part in breakdown))
    total = max(0, min(100, total))

    suggestions: list[str] = []
    for part in breakdown:
        suggestions.extend(part.get("suggestions", []))

    return {
        "score": total,
        "grade": _grade(total),
        "band": _band(total),
        "role_key": role_key,
        "role_title": role["title"],
        "experience_level": experience_level,
        "breakdown": breakdown,
        "matched_skills": sorted(have & set(role["must_have"] + role["good_to_have"])),
        "missing_must_have": skills_part["missing_must_have"],
        "missing_good_to_have": skills_part["missing_good_to_have"],
        "extra_skills": sorted(have - set(role["must_have"] + role["good_to_have"]) - SOFT_SKILLS),
        "suggestions": suggestions[:10],
    }


# --------------------------------------------------------------------------- #
# Sub-scores
# --------------------------------------------------------------------------- #


def _score_skills(have: set[str], role: dict, max_points: int) -> dict[str, Any]:
    """75% of the weight on must-haves, 25% on nice-to-haves.

    Must-haves are what gets a resume past the filter; nice-to-haves are what
    gets it to the top of the pile. Splitting them means a candidate who knows
    six trendy extras but no SQL still scores low for a backend role - which is
    exactly what a real screen does.
    """
    must = role["must_have"]
    good = role["good_to_have"]

    must_hit = sorted(have & set(must))
    good_hit = sorted(have & set(good))

    must_ratio = len(must_hit) / len(must) if must else 1.0
    good_ratio = len(good_hit) / len(good) if good else 1.0

    score = max_points * (0.75 * must_ratio + 0.25 * good_ratio)
    missing_must = sorted(set(must) - have)
    missing_good = sorted(set(good) - have)

    suggestions = []
    if missing_must:
        suggestions.append(
            "Add evidence of " + ", ".join(missing_must[:3]) +
            " - these are core requirements for this role, so a keyword filter "
            "will drop the resume without them."
        )
    if len(good_hit) < 2 and missing_good:
        suggestions.append(
            "Pick up one or two of " + ", ".join(missing_good[:3]) +
            " to stand out from other applicants who only cover the basics."
        )

    return {
        "name": "Skill match",
        "key": "skills",
        "score": round(score, 1),
        "max": max_points,
        "detail": f"{len(must_hit)}/{len(must)} required and {len(good_hit)}/{len(good)} "
                  f"preferred skills found.",
        "matched_must_have": must_hit,
        "matched_good_to_have": good_hit,
        "missing_must_have": missing_must,
        "missing_good_to_have": missing_good,
        "suggestions": suggestions,
    }


def _score_job_description(parsed: dict, jd: str, max_points: int) -> dict[str, Any]:
    """Reward literal overlap with the posting's own vocabulary.

    Real ATS ranking is closer to keyword TF than to semantics, so mirroring
    the posting's words genuinely helps. We surface the top missing terms so
    the candidate can weave them in honestly rather than keyword-stuff.
    """
    resume_text = (parsed.get("raw_text") or "").lower()
    jd_terms = _keywords(jd)
    if not jd_terms:
        return {
            "name": "Job description match", "key": "job_description",
            "score": max_points * 0.6, "max": max_points,
            "detail": "Job description was too short to extract keywords.",
            "matched": [], "missing": [], "suggestions": [],
        }

    matched = [term for term in jd_terms if term in resume_text]
    missing = [term for term in jd_terms if term not in resume_text]
    ratio = len(matched) / len(jd_terms)
    score = max_points * min(1.0, ratio / 0.6)  # 60% overlap already counts as full marks

    suggestions = []
    if missing:
        suggestions.append(
            "The posting repeatedly uses these words that your resume never does: "
            + ", ".join(missing[:6])
            + ". Where they are genuinely true of your work, use the posting's wording."
        )

    return {
        "name": "Job description match",
        "key": "job_description",
        "score": round(score, 1),
        "max": max_points,
        "detail": f"{len(matched)}/{len(jd_terms)} key terms from the posting appear in the "
                  f"resume ({ratio:.0%} overlap; 60% or more scores full marks, because no "
                  "honest resume mirrors an entire job posting).",
        "matched": matched[:20],
        "missing": missing[:20],
        "suggestions": suggestions,
    }


def _score_parseability(parsed: dict, max_points: int) -> dict[str, Any]:
    """Can machinery read this document, and are the expected sections there?"""
    sections = set(parsed.get("section_names") or [])
    contact = parsed.get("contact") or {}
    signals = parsed.get("signals") or {}
    points = 0.0
    notes: list[str] = []
    suggestions: list[str] = []

    # Required sections - 6 points
    for name in ("education", "skills", "experience"):
        if name in sections or (name == "experience" and "projects" in sections):
            points += 2
        else:
            suggestions.append(f"Add a clearly-labelled '{name.title()}' heading.")

    # Contact block - 5 points
    if contact.get("email"):
        points += 2
    else:
        suggestions.append("No email address was detected - recruiters cannot reply to you.")
    if contact.get("phone"):
        points += 1
    else:
        suggestions.append("Add a phone number in plain digits (avoid images or icons).")
    if contact.get("linkedin") or contact.get("github"):
        points += 2
    else:
        suggestions.append("Add a LinkedIn and GitHub URL as text, not as a linked icon.")

    # Length - 4 points. One page for freshers, two max for anyone.
    words = signals.get("word_count", 0)
    if 250 <= words <= 900:
        points += 4
        notes.append(f"Length is good ({words} words).")
    elif words < 250:
        points += 1
        suggestions.append(
            f"Only {words} words of readable text. Either the resume is too thin or "
            "the PDF is image-based - both score badly."
        )
    else:
        points += 2
        suggestions.append(
            f"{words} words is long for a screening resume. Cut to the strongest "
            "2 pages; freshers should aim for 1."
        )

    for warning in parsed.get("warnings") or []:
        suggestions.append(warning)
        points = max(0.0, points - 1)

    score = max_points * (points / 15.0)
    return {
        "name": "Parseability & structure",
        "key": "parseability",
        "score": round(min(score, max_points), 1),
        "max": max_points,
        "detail": "Sections found: " + (", ".join(sorted(sections)) or "none"),
        "notes": notes,
        "suggestions": suggestions,
    }


def _score_impact(parsed: dict, max_points: int) -> dict[str, Any]:
    """Do the bullets describe results, or job duties?

    This is the single biggest difference between a resume that gets a callback
    and one that does not, and it is completely under the candidate's control -
    which is why it is worth 15 points.
    """
    signals = parsed.get("signals") or {}
    verbs = signals.get("action_verbs") or []
    metrics = signals.get("quantified_results", 0)
    weak = signals.get("weak_phrases") or []
    bullets = signals.get("bullet_count", 0)

    points = 0.0
    suggestions: list[str] = []

    # Action verbs - 5
    points += min(5.0, len(verbs) * 1.0)
    if len(verbs) < 5:
        suggestions.append(
            "Start more bullets with strong verbs (built, designed, reduced, automated). "
            f"Only {len(verbs)} distinct action verbs were found."
        )

    # Quantified results - 6
    points += min(6.0, metrics * 1.5)
    if metrics < 3:
        suggestions.append(
            "Quantify your work. 'Reduced page load from 4s to 1.2s' beats "
            "'improved performance'. Aim for a number in at least 4 bullets."
        )

    # Bullet formatting - 2
    if bullets >= 6:
        points += 2
    elif bullets >= 3:
        points += 1
    else:
        suggestions.append("Use bullet points, not paragraphs. Recruiters scan for 7 seconds.")

    # Weak phrasing - 2 (lost, not gained)
    if not weak:
        points += 2
    else:
        suggestions.append(
            "Replace filler phrasing: " + ", ".join(f"'{w}'" for w in weak[:3]) +
            ". Say what you did and what changed instead."
        )

    score = max_points * (points / 15.0)
    return {
        "name": "Impact & quantification",
        "key": "impact",
        "score": round(min(score, max_points), 1),
        "max": max_points,
        "detail": f"{len(verbs)} action verbs, {metrics} quantified results, "
                  f"{bullets} bullets, {len(weak)} weak phrases.",
        "suggestions": suggestions,
    }


def _score_fit(parsed: dict, experience_level: str, max_points: int) -> dict[str, Any]:
    """Experience and education against the level being targeted."""
    expected = LEVEL_EXPECTATIONS.get(experience_level, 0.0)
    actual = float(parsed.get("experience_years") or 0.0)
    sections = set(parsed.get("section_names") or [])
    suggestions: list[str] = []

    if expected <= 0:
        # Freshers are judged on projects and education, not on years.
        experience_points = 8.0 if ("projects" in sections or "experience" in sections) else 3.0
        if "projects" not in sections:
            suggestions.append(
                "As a fresher, a Projects section is your experience section. "
                "Add 2-3 projects with what you built and what it achieved."
            )
    else:
        ratio = min(1.0, actual / expected) if expected else 1.0
        experience_points = 8.0 * ratio
        if ratio < 0.6:
            suggestions.append(
                f"This resume shows about {actual:.0f} years of experience against roughly "
                f"{expected:.0f} expected for a {experience_level} role. Make sure every "
                "role has clear start-end dates - undated roles are read as zero."
            )

    education_points = 4.0 if "education" in sections else 1.0
    extras_points = 0.0
    if "certifications" in sections:
        extras_points += 1.5
    if "achievements" in sections:
        extras_points += 1.5
    if extras_points == 0:
        suggestions.append(
            "Add certifications or achievements - they are cheap differentiators "
            "when two candidates have the same degree."
        )

    points = experience_points + education_points + extras_points
    score = max_points * (points / 15.0)
    return {
        "name": "Experience & education fit",
        "key": "fit",
        "score": round(min(score, max_points), 1),
        "max": max_points,
        "detail": f"~{actual:.1f} years detected for a '{experience_level}' target.",
        "suggestions": suggestions,
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _keywords(jd: str, limit: int = 25) -> list[str]:
    """Pick the terms a posting actually cares about.

    Known skill aliases first (they are the highest-signal words in any
    posting), then the most frequent non-stopword terms.
    """
    lowered = jd.lower()
    picked: list[str] = []

    for alias in ALIAS_TO_SKILL:
        if len(alias) < 3:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lowered):
            picked.append(alias)

    counts: dict[str, int] = {}
    for word in re.findall(r"[a-z][a-z+#.-]{2,}", lowered):
        word = word.strip(".-")
        if len(word) < 4 or word in STOPWORDS:
            continue
        counts[word] = counts.get(word, 0) + 1

    for word, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if count < 2:
            break
        if word not in picked:
            picked.append(word)

    # De-duplicate substrings ("react" vs "react.js") to keep the list honest.
    result: list[str] = []
    for term in picked:
        if not any(term != other and term in other for other in picked):
            result.append(term)
    return result[:limit]


def _grade(score: int) -> str:
    for threshold, grade in ((90, "A+"), (80, "A"), (72, "B+"), (64, "B"),
                             (56, "C+"), (45, "C"), (35, "D")):
        if score >= threshold:
            return grade
    return "F"


def _band(score: int) -> str:
    if score >= 80:
        return "Strong - likely to pass automated screening"
    if score >= 64:
        return "Good - passes most filters, room to sharpen"
    if score >= 45:
        return "Fair - will be filtered out by strict ATS setups"
    return "Weak - needs rework before applying"


# --------------------------------------------------------------------------- #
# Optional LLM narrative on top of the deterministic score
# --------------------------------------------------------------------------- #

SUMMARY_SYSTEM = (
    "You are a blunt but supportive technical recruiter reviewing a resume for a "
    "specific role. You are given a deterministic ATS score breakdown. Do not "
    "recompute or dispute the numbers - explain them like a human would and give "
    "concrete rewrites. Be specific to this resume; never give generic advice."
)


def narrative_review(parsed: dict, result: dict[str, Any]) -> dict[str, Any]:
    """Ask the LLM for a human-readable review. Falls back to a written summary.

    The fallback is a real paragraph, not an error message, so the product looks
    identical whether or not a key is configured.
    """
    fallback = {
        "verdict": result["band"],
        "strengths": _fallback_strengths(parsed, result),
        "fixes": result["suggestions"][:5],
        "one_line": (
            f"{result['score']}/100 for {result['role_title']}: "
            + (
                "missing " + ", ".join(result["missing_must_have"][:3])
                if result["missing_must_have"]
                else "core skills are covered, so focus on impact and phrasing"
            )
            + "."
        ),
    }

    llm = get_llm()
    if not llm.available:
        return fallback

    prompt = (
        f"ROLE: {result['role_title']} ({result['experience_level']} level)\n"
        f"ATS SCORE: {result['score']}/100 ({result['grade']})\n"
        f"SUB-SCORES: "
        + "; ".join(f"{p['name']} {p['score']}/{p['max']}" for p in result["breakdown"])
        + f"\nMISSING REQUIRED SKILLS: {', '.join(result['missing_must_have']) or 'none'}\n"
        f"MATCHED SKILLS: {', '.join(result['matched_skills']) or 'none'}\n\n"
        "RESUME TEXT (truncated):\n"
        + (parsed.get("raw_text") or "")[:6000]
        + "\n\nReturn JSON: {\"verdict\": str, \"one_line\": str, "
        "\"strengths\": [str, str, str], \"fixes\": [{\"issue\": str, \"rewrite\": str}]}. "
        "Each fix must quote a real line from the resume and rewrite it."
    )
    return llm.complete_json(SUMMARY_SYSTEM, prompt, fallback)


def _fallback_strengths(parsed: dict, result: dict[str, Any]) -> list[str]:
    strengths: list[str] = []
    if result["matched_skills"]:
        strengths.append(
            "Covers " + ", ".join(result["matched_skills"][:4]) + " for this role."
        )
    signals = parsed.get("signals") or {}
    if signals.get("quantified_results", 0) >= 3:
        strengths.append("Bullets include measurable results, which recruiters look for first.")
    if parsed.get("contact", {}).get("github"):
        strengths.append("A GitHub profile is linked - real code is strong evidence.")
    if result["extra_skills"]:
        strengths.append(
            "Extra breadth beyond the role: " + ", ".join(result["extra_skills"][:4]) + "."
        )
    return strengths[:4] or ["The resume parses cleanly, which many do not."]
