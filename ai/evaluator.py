"""
Answer evaluation - the part of the product that has to be trustworthy.

WHY A FIXED RUBRIC
------------------
"Rate this answer out of 10" produces a number that moves for no reason. We
score five named dimensions instead, each 0-10, each with a written reason:

    relevance     did they answer THIS question
    depth         technical substance, not surface recitation
    structure     is the answer organised (STAR for behavioural)
    specificity   concrete examples, numbers, named tools
    clarity       could a listener follow it - fillers, rambling, length

The overall score is a weighted sum, so a candidate can see exactly which
dimension cost them and practise that one thing. That is the entire product
promise: not "you scored 68" but "your depth is fine, your structure is not".

OFFLINE BEHAVIOUR
-----------------
Without an API key the heuristic scorer runs. It reads coverage of the
question's `expected_points`, answer length, filler density, STAR markers and
specificity signals. It is coarser than the model but directionally right, and
it never returns a null score.
"""

from __future__ import annotations

import re
from typing import Any

from .llm import get_llm

DIMENSIONS = ["relevance", "depth", "structure", "specificity", "clarity"]

# Behavioural answers live or die on structure; technical ones on depth.
WEIGHTS_BY_CATEGORY: dict[str, dict[str, float]] = {
    "technical":   {"relevance": 0.25, "depth": 0.35, "structure": 0.10, "specificity": 0.20, "clarity": 0.10},
    "behavioral":  {"relevance": 0.20, "depth": 0.15, "structure": 0.30, "specificity": 0.20, "clarity": 0.15},
    "situational": {"relevance": 0.25, "depth": 0.20, "structure": 0.25, "specificity": 0.15, "clarity": 0.15},
    "resume":      {"relevance": 0.20, "depth": 0.30, "structure": 0.15, "specificity": 0.25, "clarity": 0.10},
    "coding":      {"relevance": 0.20, "depth": 0.40, "structure": 0.15, "specificity": 0.15, "clarity": 0.10},
}
DEFAULT_WEIGHTS = WEIGHTS_BY_CATEGORY["technical"]

FILLERS = ["um", "uh", "erm", "like", "you know", "basically", "actually",
           "sort of", "kind of", "i mean", "so yeah", "stuff like that"]

STAR_MARKERS = {
    "situation": ["at the time", "we were", "the project was", "context", "when i was",
                  "my team was", "during"],
    "task": ["i had to", "my job", "i was responsible", "the goal", "we needed", "asked me to"],
    "action": ["i built", "i wrote", "i designed", "i decided", "i implemented", "so i",
               "i chose", "i led", "i refactored", "i tested"],
    "result": ["as a result", "which reduced", "we shipped", "the outcome", "it improved",
               "ended up", "in the end", "increased", "decreased", "saved"],
}

HEDGES = ["i think maybe", "i'm not sure", "i don't know", "probably", "i guess"]

# Detecting "did they put a number on it" is harder in speech than on paper.
# A resume writes "480ms"; a candidate says "four hundred and eighty
# milliseconds" or "from two days to about four hours". Both are quantified
# claims and both have to count, or the specificity score punishes people for
# talking like humans.
_NUMBER_WORD = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
    r"million|half|double|triple)"
)
_UNIT = (
    r"(?:%|percent|ms|millisec\w*|sec\w*|min\w*|hours?|hrs?|days?|weeks?|months?|"
    r"years?|x|times|fold|users?|customers?|requests?|queries|rows?|records?|"
    r"lines?|tests?|cases?|bugs?|people|students?|clients?|k\b|m\b|"
    r"gb|mb|kb|qps|rps)"
)
STRONG_SIGNAL_RE = re.compile(
    rf"\b(?:\d+(?:[.,]\d+)?|{_NUMBER_WORD}(?:[\s-]+{_NUMBER_WORD})*)\s*{_UNIT}\b",
    re.I,
)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def evaluate_answer(
    question: dict[str, Any],
    answer_text: str,
    *,
    duration_sec: float | None = None,
    role_title: str | None = None,
) -> dict[str, Any]:
    """Score one answer. Always returns a complete evaluation dict."""
    answer_text = (answer_text or "").strip()
    category = (question.get("category") or "technical").lower()

    if len(answer_text.split()) < 5:
        return _empty_answer_result(category)

    heuristic = _heuristic_scores(question, answer_text, duration_sec)
    result = _evaluate_with_llm(question, answer_text, category, role_title, heuristic)
    if result is None:
        result = heuristic
        result["source"] = "heuristic"
    else:
        result["source"] = "llm"

    result["overall"] = _overall(result["scores"], category)
    result["verdict"] = _verdict(result["overall"])
    result["metrics"] = _delivery_metrics(answer_text, duration_sec)
    return result


def evaluate_code(problem: dict[str, Any], code: str, language: str = "python") -> dict[str, Any]:
    """Review a coding-round submission.

    NOTE: submitted code is NEVER executed. Running untrusted code needs a real
    sandbox (container, seccomp, resource limits) and that is out of scope for
    this project, so we review it statically instead and say so in the UI. It
    is better to be honest about the limit than to run `eval()` on user input.
    """
    code = (code or "").strip()
    if len(code.splitlines()) < 2:
        return {
            **_empty_answer_result("coding"),
            "static_checks": [],
            "note": "Submitted code was empty or a single line.",
        }

    checks = _static_checks(code, language)
    heuristic = {
        "scores": {
            "relevance": 6.0 if any(c["passed"] for c in checks) else 3.0,
            "depth": min(10.0, 3.0 + 1.2 * sum(1 for c in checks if c["passed"])),
            "structure": 7.0 if re.search(r"\b(def|class|function)\b", code) else 4.0,
            "specificity": 6.0,
            "clarity": 8.0 if _has_comments(code) else 5.0,
        },
        "reasons": {c["name"]: c["detail"] for c in checks},
        "strengths": [c["name"] for c in checks if c["passed"]][:3],
        "improvements": [c["detail"] for c in checks if not c["passed"]][:4],
        "model_answer": "",
    }

    result = _evaluate_code_with_llm(problem, code, language, heuristic) or heuristic
    result.setdefault("source", "heuristic" if result is heuristic else "llm")
    result["overall"] = _overall(result["scores"], "coding")
    result["verdict"] = _verdict(result["overall"])
    result["static_checks"] = checks
    result["note"] = "Code is reviewed statically; it is not executed on the server."
    return result


def summarise_interview(
    evaluations: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    role_title: str = "the role",
) -> dict[str, Any]:
    """Roll individual answers up into the interview report.

    Per-dimension averages are what make the report useful - a single number
    tells a candidate nothing about what to practise tomorrow.
    """
    scored = [e for e in evaluations if e.get("overall") is not None]
    if not scored:
        return {
            "overall": 0, "verdict": "No answers submitted",
            "dimension_averages": {d: 0.0 for d in DIMENSIONS},
            "by_category": {}, "strengths": [], "improvements": [],
            "answered": 0, "total": len(questions),
        }

    dimension_averages = {
        dimension: round(
            sum(float(e["scores"].get(dimension, 0)) for e in scored) / len(scored), 1
        )
        for dimension in DIMENSIONS
    }

    by_category: dict[str, list[float]] = {}
    for evaluation, question in zip(evaluations, questions):
        if evaluation.get("overall") is None:
            continue
        by_category.setdefault((question.get("category") or "technical"), []).append(
            float(evaluation["overall"])
        )

    overall = round(sum(float(e["overall"]) for e in scored) / len(scored))

    strengths: list[str] = []
    improvements: list[str] = []
    for evaluation in scored:
        strengths.extend(evaluation.get("strengths") or [])
        improvements.extend(evaluation.get("improvements") or [])

    best = max(dimension_averages, key=lambda d: dimension_averages[d])
    worst = min(dimension_averages, key=lambda d: dimension_averages[d])

    return {
        "overall": overall,
        "verdict": _verdict(overall),
        "dimension_averages": dimension_averages,
        "by_category": {k: round(sum(v) / len(v)) for k, v in by_category.items()},
        "strongest_dimension": best,
        "weakest_dimension": worst,
        "headline": (
            f"{overall}/100 for {role_title}. Strongest: {best} "
            f"({dimension_averages[best]}/10). Weakest: {worst} "
            f"({dimension_averages[worst]}/10)."
        ),
        "strengths": _dedupe(strengths)[:5],
        "improvements": _dedupe(improvements)[:6],
        "answered": len(scored),
        "total": len(questions),
    }


# --------------------------------------------------------------------------- #
# Heuristic engine
# --------------------------------------------------------------------------- #


def _heuristic_scores(
    question: dict[str, Any],
    answer: str,
    duration_sec: float | None,
) -> dict[str, Any]:
    lowered = answer.lower()
    words = answer.split()
    word_count = len(words)
    category = (question.get("category") or "technical").lower()
    expected = [str(p) for p in (question.get("expected_points") or [])]

    covered, missed = _coverage(expected, lowered)
    coverage_ratio = len(covered) / len(expected) if expected else 0.5

    # --- relevance: did they hit the points the question was asking for? ---
    question_terms = _content_words(question.get("text", ""))
    echo = len(question_terms & set(_tokens(lowered))) / (len(question_terms) or 1)
    relevance = 3.0 + 5.0 * coverage_ratio + 2.0 * min(1.0, echo * 2)

    # --- depth: length with diminishing returns, plus technical vocabulary ---
    length_component = min(1.0, word_count / 130.0)
    technical_terms = len(re.findall(
        r"\b(complexity|o\(|latency|throughput|index|cache|async|thread|schema|"
        r"trade-?off|scal\w+|test\w*|deploy\w*|architect\w*|algorithm|memory|"
        r"validat\w+|optimi[sz]\w+|concurren\w+)\b", lowered))
    depth = 2.0 + 4.0 * length_component + min(3.0, technical_terms * 0.6) + 1.0 * coverage_ratio

    # --- structure: STAR for behavioural, ordering markers for technical ---
    if category in ("behavioral", "situational", "resume"):
        star_hits = sum(
            1 for markers in STAR_MARKERS.values() if any(m in lowered for m in markers)
        )
        structure = 2.0 + 2.0 * star_hits
    else:
        connectives = len(re.findall(
            r"\b(first|second|then|next|finally|because|therefore|however|"
            r"for example|the reason|on the other hand)\b", lowered))
        structure = 4.0 + min(5.0, connectives * 1.2)

    # --- specificity: numbers, named tools, first-person ownership ---
    metrics = len(STRONG_SIGNAL_RE.findall(answer))
    proper_nouns = len(set(re.findall(r"\b[A-Z][a-zA-Z+#.]{2,}\b", answer)))
    ownership = len(re.findall(r"\bi (?:built|wrote|designed|implemented|chose|led|fixed)\b", lowered))
    specificity = 2.0 + min(3.0, metrics * 1.5) + min(3.0, proper_nouns * 0.5) + min(2.0, ownership * 1.0)

    # --- clarity: fillers, hedging, rambling, speaking pace ---
    filler_count = sum(lowered.count(f) for f in FILLERS)
    filler_rate = filler_count / max(word_count, 1)
    hedge_count = sum(lowered.count(h) for h in HEDGES)
    clarity = 9.0 - min(4.0, filler_rate * 120) - min(2.0, hedge_count * 0.8)
    if word_count < 30:
        clarity -= 2.0          # too short to have said anything
    if word_count > 420:
        clarity -= 1.5          # rambling
    if duration_sec and duration_sec > 5:
        wpm = word_count / (duration_sec / 60.0)
        if wpm > 190 or wpm < 80:
            clarity -= 1.0      # rushing or dragging

    scores = {
        "relevance": _clamp(relevance),
        "depth": _clamp(depth),
        "structure": _clamp(structure),
        "specificity": _clamp(specificity),
        "clarity": _clamp(clarity),
    }

    strengths: list[str] = []
    improvements: list[str] = []

    if covered:
        strengths.append("Covered the key points: " + ", ".join(covered[:3]) + ".")
    if metrics:
        strengths.append("Used concrete numbers, which makes the claim believable.")
    if ownership:
        strengths.append("Made your own contribution clear ('I built/designed...').")

    if missed:
        improvements.append("Did not mention: " + ", ".join(missed[:3]) + ".")
    if word_count < 60:
        improvements.append(
            f"Only {word_count} words. Aim for 90-180 - enough for context, action and result."
        )
    if word_count > 400:
        improvements.append("Too long. Interviewers stop listening after about 2 minutes; edit down.")
    if filler_rate > 0.03:
        improvements.append(
            f"{filler_count} filler words ('um', 'like', 'basically'). Pause instead - silence sounds confident."
        )
    if category in ("behavioral", "situational", "resume") and scores["structure"] < 6:
        improvements.append("Use STAR: Situation, Task, Action, Result. The Result is what gets remembered.")
    if not metrics and category != "technical":
        improvements.append("Add one number to the result - 'cut load time from 4s to 1.2s'.")

    return {
        "scores": scores,
        "reasons": {
            "relevance": f"Covered {len(covered)}/{len(expected) or 1} expected points.",
            "depth": f"{word_count} words with {technical_terms} technical terms.",
            "structure": "STAR/ordering markers detected." if scores["structure"] >= 6
                         else "Little visible structure.",
            "specificity": f"{metrics} quantified claims, {proper_nouns} named tools.",
            "clarity": f"{filler_count} fillers over {word_count} words.",
        },
        "covered_points": covered,
        "missed_points": missed,
        "strengths": strengths[:4],
        "improvements": improvements[:5],
        "model_answer": _model_answer_hint(question, missed),
    }


def _coverage(expected: list[str], lowered_answer: str) -> tuple[list[str], list[str]]:
    """Which expected talking points did the answer actually touch?

    A point counts as covered when at least half of its content words appear.
    Loose on purpose: candidates paraphrase, and punishing synonyms would make
    the score feel arbitrary.
    """
    covered, missed = [], []
    answer_tokens = set(_tokens(lowered_answer))
    for point in expected:
        terms = _content_words(point)
        if not terms:
            continue
        hits = len(terms & answer_tokens)
        (covered if hits >= max(1, len(terms) // 2) else missed).append(point)
    return covered, missed


_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "be", "it", "that", "this", "with", "as", "at", "by", "from",
    "you", "your", "they", "their", "have", "has", "had", "do", "does", "did",
    "what", "when", "how", "why", "would", "could", "should", "can", "will",
    "me", "my", "i", "we", "us", "our", "about", "not", "but", "if", "so",
    "tell", "give", "describe", "explain", "walk", "think", "one", "some",
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#]+", text.lower())


def _content_words(text: str) -> set[str]:
    return {t for t in _tokens(text) if len(t) > 2 and t not in _STOP}


def _delivery_metrics(answer: str, duration_sec: float | None) -> dict[str, Any]:
    words = answer.split()
    lowered = answer.lower()
    filler_count = sum(lowered.count(f) for f in FILLERS)
    metrics: dict[str, Any] = {
        "word_count": len(words),
        "filler_count": filler_count,
        "filler_rate": round(filler_count / max(len(words), 1), 4),
        "quantified_claims": len(STRONG_SIGNAL_RE.findall(answer)),
    }
    if duration_sec and duration_sec > 1:
        metrics["duration_sec"] = round(duration_sec, 1)
        metrics["words_per_minute"] = round(len(words) / (duration_sec / 60.0))
        metrics["pace"] = (
            "too fast" if metrics["words_per_minute"] > 190
            else "too slow" if metrics["words_per_minute"] < 90
            else "good"
        )
    return metrics


def _model_answer_hint(question: dict[str, Any], missed: list[str]) -> str:
    expected = [str(p) for p in (question.get("expected_points") or [])]
    if not expected:
        return ""
    lead = "A strong answer covers: " + "; ".join(expected) + "."
    if missed:
        lead += " You left out: " + "; ".join(missed[:3]) + "."
    return lead


def _empty_answer_result(category: str) -> dict[str, Any]:
    scores = {dimension: 0.0 for dimension in DIMENSIONS}
    return {
        "scores": scores,
        "overall": 0,
        "verdict": "No answer",
        "reasons": {d: "No answer was given." for d in DIMENSIONS},
        "covered_points": [],
        "missed_points": [],
        "strengths": [],
        "improvements": ["Give an answer, even a partial one. Saying 'I don't know, but here is "
                         "how I'd find out' scores far better than silence."],
        "model_answer": "",
        "metrics": {"word_count": 0},
        "source": "heuristic",
    }


# --------------------------------------------------------------------------- #
# Static code checks (no execution)
# --------------------------------------------------------------------------- #


def _static_checks(code: str, language: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    if language == "python":
        try:
            import ast

            ast.parse(code)
            check("Parses", True, "Code is syntactically valid Python.")
        except SyntaxError as exc:
            check("Parses", False, f"Syntax error on line {exc.lineno}: {exc.msg}")
    elif language == "sql":
        check("Looks like SQL", bool(re.search(r"\bselect\b", code, re.I)),
              "A SELECT statement was found." if re.search(r"\bselect\b", code, re.I)
              else "No SELECT statement found.")

    check("Has a function or class", bool(re.search(r"\b(def|class|function)\b", code)),
          "Solution is wrapped in a named unit." if re.search(r"\b(def|class|function)\b", code)
          else "Wrap the solution in a function - interviewers expect a callable answer.")

    check("Not a stub", "pass" not in code.split() and "your code here" not in code.lower(),
          "The starter stub was replaced." if "your code here" not in code.lower()
          else "The starter comment is still there - the solution looks unfinished.")

    check("Handles edge cases", bool(re.search(r"\b(if not|len\(|is None|== 0|empty|raise)\b", code)),
          "Some guarding of edge cases is present."
          if re.search(r"\b(if not|len\(|is None|== 0|empty|raise)\b", code)
          else "No empty/null input handling is visible.")

    quadratic = bool(re.search(r"for .+:\s*\n\s+for .+:", code))
    check("Avoids obvious O(n^2)", not quadratic,
          "Nested loops found - state whether that is intentional and what the complexity is."
          if quadratic else "No obvious nested-loop scan.")

    return checks


def _has_comments(code: str) -> bool:
    return bool(re.search(r"(^|\s)(#|//|--)\s*\S", code)) or '"""' in code


# --------------------------------------------------------------------------- #
# LLM engine
# --------------------------------------------------------------------------- #

EVAL_SYSTEM = (
    "You are a senior engineer grading a mock-interview answer. Be fair and "
    "concrete: quote the candidate's own words when you praise or criticise. "
    "Score each dimension 0-10 where 5 is an average junior candidate and 8+ is "
    "genuinely strong. Never invent things the candidate did not say. Feedback "
    "must be usable tomorrow morning, not vague encouragement."
)


def _evaluate_with_llm(
    question: dict[str, Any],
    answer: str,
    category: str,
    role_title: str | None,
    heuristic: dict[str, Any],
) -> dict[str, Any] | None:
    llm = get_llm()
    if not llm.available:
        return None

    prompt = (
        f"ROLE: {role_title or 'software engineer'}\n"
        f"QUESTION CATEGORY: {category}\n"
        f"QUESTION: {question.get('text', '')}\n"
        f"WHAT A STRONG ANSWER SHOULD CONTAIN: "
        + "; ".join(str(p) for p in (question.get("expected_points") or []))
        + f"\n\nCANDIDATE ANSWER (transcribed from speech, so ignore small transcription errors):\n"
        f"\"\"\"{answer[:4000]}\"\"\"\n\n"
        "Return JSON: {\"scores\": {\"relevance\": n, \"depth\": n, \"structure\": n, "
        "\"specificity\": n, \"clarity\": n}, \"reasons\": {same five keys: one sentence each}, "
        "\"covered_points\": [str], \"missed_points\": [str], \"strengths\": [str], "
        "\"improvements\": [str], \"model_answer\": \"a 90-second model answer in first person\"}"
    )

    data = llm.complete_json(EVAL_SYSTEM, prompt, fallback=None, max_tokens=1600)
    if not isinstance(data, dict) or not isinstance(data.get("scores"), dict):
        return None

    scores = {}
    for dimension in DIMENSIONS:
        try:
            scores[dimension] = _clamp(float(data["scores"].get(dimension, heuristic["scores"][dimension])))
        except (TypeError, ValueError):
            scores[dimension] = heuristic["scores"][dimension]

    return {
        "scores": scores,
        "reasons": {d: str(data.get("reasons", {}).get(d, "")) for d in DIMENSIONS},
        "covered_points": [str(p) for p in (data.get("covered_points") or [])][:6],
        "missed_points": [str(p) for p in (data.get("missed_points") or [])][:6],
        "strengths": [str(s) for s in (data.get("strengths") or [])][:4],
        "improvements": [str(s) for s in (data.get("improvements") or [])][:5],
        "model_answer": str(data.get("model_answer") or heuristic["model_answer"]),
    }


CODE_SYSTEM = (
    "You are reviewing a coding-interview submission. You cannot run the code. "
    "Reason about correctness by reading it: trace the logic on the example, "
    "check edge cases, and state the time and space complexity. Be direct about "
    "whether this would pass a real interview."
)


def _evaluate_code_with_llm(
    problem: dict[str, Any],
    code: str,
    language: str,
    heuristic: dict[str, Any],
) -> dict[str, Any] | None:
    llm = get_llm()
    if not llm.available:
        return None

    prompt = (
        f"PROBLEM: {problem.get('title')}\n{problem.get('prompt')}\n"
        f"EXAMPLES: {problem.get('examples')}\n"
        f"WHAT A STRONG SOLUTION SHOWS: "
        + "; ".join(str(p) for p in (problem.get("expected_points") or []))
        + f"\n\nSUBMISSION ({language}):\n```\n{code[:4000]}\n```\n\n"
        "Return JSON: {\"scores\": {\"relevance\": n, \"depth\": n, \"structure\": n, "
        "\"specificity\": n, \"clarity\": n}, \"reasons\": {same keys}, "
        "\"correct\": true|false, \"complexity\": \"O(...) time, O(...) space\", "
        "\"failing_cases\": [str], \"strengths\": [str], \"improvements\": [str], "
        "\"model_answer\": \"the idiomatic solution with a one-line explanation\"}"
    )

    data = llm.complete_json(CODE_SYSTEM, prompt, fallback=None, max_tokens=1800)
    if not isinstance(data, dict) or not isinstance(data.get("scores"), dict):
        return None

    scores = {}
    for dimension in DIMENSIONS:
        try:
            scores[dimension] = _clamp(float(data["scores"].get(dimension, heuristic["scores"][dimension])))
        except (TypeError, ValueError):
            scores[dimension] = heuristic["scores"][dimension]

    return {
        "scores": scores,
        "reasons": {d: str(data.get("reasons", {}).get(d, "")) for d in DIMENSIONS},
        "correct": bool(data.get("correct", False)),
        "complexity": str(data.get("complexity", "")),
        "failing_cases": [str(c) for c in (data.get("failing_cases") or [])][:5],
        "covered_points": [],
        "missed_points": [],
        "strengths": [str(s) for s in (data.get("strengths") or [])][:4],
        "improvements": [str(s) for s in (data.get("improvements") or [])][:5],
        "model_answer": str(data.get("model_answer") or ""),
        "source": "llm",
    }


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def _clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return round(max(low, min(high, value)), 1)


def _overall(scores: dict[str, float], category: str) -> int:
    weights = WEIGHTS_BY_CATEGORY.get(category, DEFAULT_WEIGHTS)
    total = sum(float(scores.get(d, 0)) * w for d, w in weights.items())
    return int(round(total * 10))


def _verdict(overall: int) -> str:
    if overall >= 85:
        return "Excellent - would pass this round"
    if overall >= 70:
        return "Good - a few gaps to tighten"
    if overall >= 55:
        return "Average - answer is there, delivery and depth are not"
    if overall >= 35:
        return "Weak - needs structure and specifics"
    return "Poor - practise this question again"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result
