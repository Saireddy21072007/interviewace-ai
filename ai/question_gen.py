"""
Interview question generation.

TWO ENGINES, ONE INTERFACE
--------------------------
`generate_questions()` always returns the same shape. Internally it prefers the
LLM (questions that quote the candidate's actual projects are far better) and
falls back to a curated bank keyed on the skills we detected in the resume.

The fallback is not a stub. It is a real question bank with expected talking
points, so an offline demo still runs a credible interview - the questions are
just less personalised.

QUESTION SHAPE
--------------
    {
      "index": 1,
      "category": "technical" | "behavioral" | "situational" | "resume" | "coding",
      "skill": "React",
      "difficulty": "easy" | "medium" | "hard",
      "text": "...",
      "expected_points": ["...", "..."],   # what a good answer must contain
      "time_limit_sec": 180,
      "source": "llm" | "bank"
    }
"""

from __future__ import annotations

import random
import re
from typing import Any

from .llm import get_llm
from .skills_db import company_or_default, role_or_default

DIFFICULTY_ORDER = ["easy", "medium", "hard"]
TIME_LIMITS = {"easy": 120, "medium": 180, "hard": 240, "coding": 900}


# --------------------------------------------------------------------------- #
# 1. Curated bank - the offline engine
# --------------------------------------------------------------------------- #

TECHNICAL_BANK: dict[str, list[tuple[str, str, list[str]]]] = {
    "Python": [
        ("easy", "What is the difference between a list and a tuple, and when would you pick one over the other?",
         ["mutability", "tuples are hashable so they can be dict keys", "a concrete example"]),
        ("medium", "Walk me through what a decorator is. Give an example of one you have written or used.",
         ["a function that wraps another", "closures", "functools.wraps", "a real use like timing or auth"]),
        ("hard", "Explain the GIL. When does it actually hurt you, and what do you do about it?",
         ["one thread executes bytecode at a time", "hurts CPU-bound work, not I/O-bound",
          "multiprocessing / native extensions / async for I/O"]),
    ],
    "JavaScript": [
        ("easy", "What is the difference between let, const and var?",
         ["block vs function scope", "hoisting and the temporal dead zone", "const binds, it does not freeze"]),
        ("medium", "Explain the event loop. Why does a setTimeout with 0ms not run immediately?",
         ["call stack", "task vs microtask queue", "promises resolve before timers"]),
        ("hard", "What is a closure, and describe a bug you have had because of one.",
         ["function keeps its lexical scope", "classic loop-variable capture", "memory retention"]),
    ],
    "TypeScript": [
        ("medium", "What problem does TypeScript solve that tests do not, and where does it not help?",
         ["errors at compile time", "types are erased at runtime", "external data still needs validation"]),
        ("hard", "When would you reach for a generic instead of `any` or a union?",
         ["preserving the relationship between input and output types", "constraint with extends"]),
    ],
    "React": [
        ("easy", "What is the difference between state and props?",
         ["props come from the parent and are read-only", "state is owned by the component", "re-render triggers"]),
        ("medium", "How do you stop a component from re-rendering unnecessarily, and how do you know it is happening?",
         ["React.memo / useMemo / useCallback", "stable dependencies", "profiler measurement before optimising"]),
        ("hard", "Explain the dependency array of useEffect. Describe a bug you have caused with it.",
         ["effect re-runs when a dependency changes", "stale closures", "cleanup function", "infinite loops"]),
    ],
    "Node.js": [
        ("medium", "Node is single-threaded - how does it serve thousands of concurrent requests?",
         ["non-blocking I/O", "event loop and libuv thread pool", "CPU-bound work blocks everything"]),
    ],
    "SQL": [
        ("easy", "What is the difference between INNER JOIN and LEFT JOIN?",
         ["only matching rows vs all left rows", "NULLs on the right side", "an example"]),
        ("medium", "A query that used to take 100ms now takes 8 seconds. How do you find out why?",
         ["EXPLAIN / query plan", "missing or unusable index", "data growth and statistics", "N+1 from the app"]),
        ("hard", "When is an index a bad idea?",
         ["write amplification", "low-cardinality columns", "storage cost", "planner may ignore it"]),
    ],
    "Database Design": [
        ("medium", "Walk me through how you would design the schema for this interview-prep product.",
         ["users, resumes, interviews, questions, answers", "foreign keys", "one-to-many relationships",
          "what you would index"]),
        ("hard", "When would you deliberately denormalise?",
         ["read-heavy access patterns", "expensive joins", "accepting update anomalies knowingly"]),
    ],
    "REST APIs": [
        ("easy", "What do 200, 201, 400, 401, 403, 404 and 500 each mean?",
         ["created vs ok", "401 is unauthenticated, 403 is unauthorised", "4xx client vs 5xx server"]),
        ("medium", "How do you version an API without breaking existing clients?",
         ["URI or header versioning", "additive changes only", "deprecation window"]),
        ("hard", "Design the endpoints for a resume-upload and analysis flow. What is idempotent and what is not?",
         ["POST creates, PUT replaces", "async job + status polling for slow analysis", "retry safety"]),
    ],
    "System Design": [
        ("medium", "How would you scale this app from 100 users to 100,000?",
         ["find the bottleneck first", "stateless app servers behind a load balancer",
          "database read replicas / caching", "async workers for slow AI calls"]),
        ("hard", "Design a system that runs AI mock interviews for 10,000 concurrent users.",
         ["queueing model inference", "streaming audio", "cost per interview", "graceful degradation"]),
    ],
    "Data Structures": [
        ("easy", "When would you use a hash map over an array?",
         ["O(1) average lookup by key", "no ordering", "hash collisions and worst case"]),
        ("medium", "How would you detect a cycle in a linked list in O(1) space?",
         ["fast and slow pointers", "why they must meet", "complexity"]),
        ("hard", "You need the top 100 items from a stream of a billion. What structure and why?",
         ["min-heap of size k", "O(n log k)", "why sorting everything is wrong"]),
    ],
    "Algorithms": [
        ("medium", "Explain the time and space complexity of your favourite sorting algorithm and when it is the wrong choice.",
         ["big-O of best/average/worst", "stability", "small-input or nearly-sorted cases"]),
        ("hard", "How do you recognise a problem as dynamic programming?",
         ["optimal substructure", "overlapping subproblems", "memo vs tabulation"]),
    ],
    "Operating Systems": [
        ("medium", "What is the difference between a process and a thread?",
         ["separate vs shared memory space", "context-switch cost", "shared state means locks"]),
        ("hard", "What causes a deadlock and how do you prevent one?",
         ["the four Coffman conditions", "lock ordering", "timeouts"]),
    ],
    "Computer Networks": [
        ("easy", "What happens between typing a URL and the page appearing?",
         ["DNS", "TCP + TLS handshake", "HTTP request/response", "render"]),
        ("medium", "TCP vs UDP - which would you use for live interview audio, and why?",
         ["ordering and retransmission vs latency", "audio prefers UDP", "jitter buffers"]),
    ],
    "Object Oriented Design": [
        ("medium", "Explain SOLID with an example from your own code.",
         ["names all five or the ones used", "a concrete refactor", "why it helped"]),
    ],
    "Docker": [
        ("easy", "What problem does Docker actually solve for a team?",
         ["same environment everywhere", "image vs container", "dependency isolation"]),
        ("medium", "How do you keep a Python image small and fast to rebuild?",
         ["slim base image", "layer ordering so deps cache", "multi-stage build", ".dockerignore"]),
    ],
    "CI/CD": [
        ("medium", "What runs in your pipeline before code reaches production?",
         ["lint, tests, build", "branch protection", "rollback plan"]),
    ],
    "AWS": [
        ("medium", "How would you deploy this project on AWS, and what would it cost?",
         ["compute choice and why", "managed database", "object storage for uploads", "rough monthly cost"]),
    ],
    "Git": [
        ("easy", "What is the difference between merge and rebase?",
         ["merge commit preserves history", "rebase rewrites for a linear history", "never rebase shared branches"]),
    ],
    "Testing": [
        ("medium", "What do you test, and what do you deliberately not test?",
         ["behaviour over implementation", "the test pyramid", "cost of brittle tests"]),
    ],
    "Machine Learning": [
        ("easy", "Explain overfitting to a non-technical person, then to me.",
         ["memorising vs generalising", "train/validation gap", "regularisation, more data, simpler model"]),
        ("medium", "Your model is 97% accurate and useless. How is that possible?",
         ["class imbalance", "accuracy is the wrong metric", "precision/recall/F1", "the base rate"]),
        ("hard", "How do you know your validation score is not lying to you?",
         ["data leakage", "temporal splits for time series", "duplicate rows across splits", "test set reuse"]),
    ],
    "Deep Learning": [
        ("medium", "Your training loss falls but validation loss rises. What do you do?",
         ["overfitting", "early stopping / dropout / augmentation", "check the data first"]),
        ("hard", "Why do we use batch normalisation, and where does it fail?",
         ["stabilises distributions", "allows higher learning rates", "small batch sizes / RNNs"]),
    ],
    "Model Evaluation": [
        ("medium", "When is precision more important than recall? Give a real example.",
         ["cost of false positive vs false negative", "a concrete domain", "threshold tuning"]),
    ],
    "NLP": [
        ("medium", "What does an embedding actually represent?",
         ["dense vector in learned space", "similarity as distance", "context vs static embeddings"]),
    ],
    "LLMs": [
        ("medium", "How do you stop an LLM feature from hallucinating in production?",
         ["grounding / retrieval", "structured output validation", "evals before shipping", "fallbacks"]),
        ("hard", "How would you evaluate the answer-scoring feature of a product like this one?",
         ["labelled gold set", "agreement with human raters", "regression tests on prompt changes"]),
    ],
    "Prompt Engineering": [
        ("medium", "What separates a prompt that works in a demo from one that works in production?",
         ["explicit output schema", "edge cases and refusals", "evaluated on real inputs", "versioning"]),
    ],
    "Statistics": [
        ("medium", "Explain p-value to a product manager who wants to ship on day two of an A/B test.",
         ["probability under the null", "not the probability of being right", "peeking inflates false positives"]),
    ],
    "Pandas": [
        ("easy", "How do you find and handle missing values in a dataframe?",
         ["isna / sum", "drop vs impute and the trade-off", "why the values are missing matters"]),
    ],
    "Linux": [
        ("medium", "A server is at 100% CPU. Walk me through your first five commands.",
         ["top/htop", "identify the process", "logs", "recent deploys", "restart is the last resort"]),
    ],
}

BEHAVIORAL_BANK: list[tuple[str, list[str]]] = [
    ("Tell me about yourself.",
     ["a 60-90 second arc", "what you build", "why this role", "no life story"]),
    ("Tell me about a project you are proud of. What was your specific contribution?",
     ["situation and goal", "what YOU did, not the team", "the outcome", "what you would change"]),
    ("Describe a time you disagreed with a teammate. How did it end?",
     ["the actual disagreement", "how you argued the case", "the resolution", "no blaming"]),
    ("Tell me about a time you failed or shipped a bug to users.",
     ["owns it without excuses", "the impact", "how it was fixed", "what changed afterwards"]),
    ("What is something technical you taught yourself recently, and how?",
     ["a specific topic", "the actual method", "evidence it stuck - a project or result"]),
    ("Describe a time you had to work under a tight deadline.",
     ["what was cut and why", "how priorities were chosen", "the outcome"]),
    ("Why do you want this role, at this company?",
     ["specific to the company, not generic", "connects to their work", "honest motivation"]),
    ("Tell me about a time you received hard feedback.",
     ["the feedback itself", "the initial reaction", "the concrete change made"]),
]

SITUATIONAL_BANK: list[tuple[str, list[str]]] = [
    ("You are two days from a release and find a bug that affects 5% of users. What do you do?",
     ["assesses severity, not just count", "communicates early", "ship-with-known-issue vs delay trade-off"]),
    ("A senior engineer's code review comment is wrong. How do you handle it?",
     ["verifies first", "disagrees with evidence, in public or private appropriately", "keeps it about the code"]),
    ("You have been given a task with unclear requirements and the PM is unreachable. What now?",
     ["writes down assumptions", "builds the smallest thing that can be validated", "does not block silently"]),
    ("Production is down and you are on call at 2am. Talk me through your first ten minutes.",
     ["restore service before root cause", "check recent changes", "communicate status", "rollback"]),
    ("Halfway through a sprint you realise your approach will not work. What do you do?",
     ["raises it immediately", "brings options, not just a problem", "estimates the new cost"]),
]

# Templates for questions grounded in the candidate's own resume.
RESUME_TEMPLATES = [
    ("Your resume lists {skill}. Tell me about the hardest problem you solved with it.",
     ["a specific problem", "the approach and alternatives", "the outcome", "genuine depth, not buzzwords"]),
    ("You mention {skill} - if I gave you a blank editor right now, what would you build with it in an hour?",
     ["concrete plan", "realistic scope", "shows hands-on familiarity"]),
    ("How would you explain {skill} to a first-year student?",
     ["simple accurate analogy", "no jargon", "shows real understanding"]),
    ("Where has {skill} let you down, or what do you dislike about it?",
     ["a real limitation", "shows experience past tutorials", "an alternative considered"]),
]

PROJECT_TEMPLATES = [
    ("Walk me through this from your resume: \"{line}\". What was the architecture?",
     ["clear architecture", "why those choices", "what they personally built"]),
    ("About \"{line}\" - what broke, and how did you find out?",
     ["a real failure", "debugging method", "the fix"]),
    ("If you rebuilt \"{line}\" today, what would you do differently?",
     ["honest self-critique", "specific technical change", "reasoning"]),
]


# --------------------------------------------------------------------------- #
# 2. Public API
# --------------------------------------------------------------------------- #


def generate_questions(
    parsed_resume: dict[str, Any] | None,
    role_key: str | None = None,
    company_key: str | None = None,
    count: int = 8,
    difficulty: str = "medium",
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Return `count` interview questions for this candidate.

    `parsed_resume` may be None - the caller might be practising for a role
    before uploading anything, and that should still work.
    """
    role_key, role = role_or_default(role_key)
    company_key, company = company_or_default(company_key)
    count = max(1, min(20, count))
    rng = random.Random(seed)

    skills = list((parsed_resume or {}).get("skill_list") or [])
    relevant = [s for s in skills if s in role["must_have"] + role["good_to_have"]]
    focus_skills = relevant or role["must_have"]

    plan = _plan_categories(company["mix"], count, has_resume=bool(skills))

    llm_questions = _generate_with_llm(parsed_resume, role, company, plan, difficulty)
    if llm_questions:
        return _finalise(llm_questions[:count], difficulty)

    return _finalise(
        _generate_from_bank(parsed_resume, focus_skills, plan, difficulty, rng),
        difficulty,
    )


def _plan_categories(mix: dict[str, int], count: int, has_resume: bool) -> list[str]:
    """Turn a company's category weights into an ordered question plan.

    The order matters: warm up with an easy behavioural, put the technical
    core in the middle, and close with something reflective - the same shape a
    real interviewer uses.
    """
    weights = dict(mix)
    if not has_resume:
        weights.pop("resume", None)
    total = sum(weights.values()) or 1

    plan: list[str] = []
    for category, weight in weights.items():
        plan.extend([category] * max(1, round(count * weight / total)))

    plan = plan[:count]
    while len(plan) < count:
        plan.append("technical")

    # Interview-shaped ordering.
    order = {"behavioral": 0, "resume": 1, "technical": 2, "situational": 3}
    opener = next((c for c in plan if c == "behavioral"), None)
    rest = plan[:]
    if opener:
        rest.remove(opener)
    rest.sort(key=lambda c: order.get(c, 5))
    return ([opener] if opener else []) + rest


def _finalise(questions: list[dict[str, Any]], difficulty: str) -> list[dict[str, Any]]:
    for index, question in enumerate(questions, start=1):
        question["index"] = index
        question.setdefault("difficulty", difficulty)
        question.setdefault("category", "technical")
        question.setdefault("expected_points", [])
        question.setdefault("skill", None)
        question["time_limit_sec"] = TIME_LIMITS.get(question["difficulty"], 180)
    return questions


# --------------------------------------------------------------------------- #
# 3. The bank engine
# --------------------------------------------------------------------------- #


def _generate_from_bank(
    parsed_resume: dict[str, Any] | None,
    focus_skills: list[str],
    plan: list[str],
    difficulty: str,
    rng: random.Random,
) -> list[dict[str, Any]]:
    used_texts: set[str] = set()
    questions: list[dict[str, Any]] = []
    skill_cycle = list(focus_skills) or ["Problem Solving"]
    rng.shuffle(skill_cycle)
    project_lines = _project_lines(parsed_resume)

    for position, category in enumerate(plan):
        skill = skill_cycle[position % len(skill_cycle)]
        question = None

        if category == "technical":
            question = _pick_technical(skill, difficulty, used_texts, rng, skill_cycle)
        elif category == "behavioral":
            question = _pick_from(BEHAVIORAL_BANK, "behavioral", used_texts, rng, difficulty="easy")
        elif category == "situational":
            question = _pick_from(SITUATIONAL_BANK, "situational", used_texts, rng, difficulty="medium")
        elif category == "resume":
            question = _pick_resume(skill, project_lines, used_texts, rng)

        if question is None:  # every bank exhausted - fall back to behavioural
            question = _pick_from(BEHAVIORAL_BANK, "behavioral", used_texts, rng, difficulty="easy")
        if question is None:
            continue

        used_texts.add(question["text"])
        questions.append(question)

    return questions


def _pick_technical(
    skill: str,
    difficulty: str,
    used: set[str],
    rng: random.Random,
    fallback_skills: list[str],
) -> dict[str, Any] | None:
    """Prefer the requested difficulty for this skill, then any difficulty,
    then any other skill the candidate actually has."""
    for candidate_skill in [skill, *fallback_skills]:
        entries = TECHNICAL_BANK.get(candidate_skill)
        if not entries:
            continue
        pools = (
            [e for e in entries if e[0] == difficulty and e[1] not in used],
            [e for e in entries if e[1] not in used],
        )
        for pool in pools:
            if pool:
                level, text, points = rng.choice(pool)
                return {
                    "category": "technical", "skill": candidate_skill,
                    "difficulty": level, "text": text,
                    "expected_points": points, "source": "bank",
                }
    return None


def _pick_from(
    bank: list[tuple[str, list[str]]],
    category: str,
    used: set[str],
    rng: random.Random,
    difficulty: str,
) -> dict[str, Any] | None:
    pool = [entry for entry in bank if entry[0] not in used]
    if not pool:
        return None
    text, points = rng.choice(pool)
    return {
        "category": category, "skill": None, "difficulty": difficulty,
        "text": text, "expected_points": points, "source": "bank",
    }


def _pick_resume(
    skill: str,
    project_lines: list[str],
    used: set[str],
    rng: random.Random,
) -> dict[str, Any] | None:
    if project_lines and rng.random() < 0.6:
        template, points = rng.choice(PROJECT_TEMPLATES)
        line = rng.choice(project_lines)
        text = template.format(line=line)
        if text not in used:
            return {"category": "resume", "skill": None, "difficulty": "medium",
                    "text": text, "expected_points": points, "source": "bank"}

    for template, points in rng.sample(RESUME_TEMPLATES, len(RESUME_TEMPLATES)):
        text = template.format(skill=skill)
        if text not in used:
            return {"category": "resume", "skill": skill, "difficulty": "medium",
                    "text": text, "expected_points": points, "source": "bank"}
    return None


def _project_lines(parsed_resume: dict[str, Any] | None) -> list[str]:
    """Pull quotable bullet points out of the projects/experience sections.

    Resume bullets wrap across several physical lines, so we re-join a line
    into the bullet above it unless it starts a new bullet. Quoting half a
    sentence back at a candidate ("...time from 480ms to 120ms by adding") is
    the fastest way to make the product look broken.
    """
    if not parsed_resume:
        return []
    sections = parsed_resume.get("sections") or {}
    blob = "\n".join(sections.get(name, "") for name in ("projects", "experience"))

    bullets: list[str] = []
    for raw in blob.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith(("-", "*", "•")):
            bullets.append(stripped.lstrip("-*• ").strip())
        elif bullets and not _looks_like_heading(stripped):
            bullets[-1] = f"{bullets[-1]} {stripped}"

    lines = []
    for bullet in bullets:
        line = re.sub(r"\s+", " ", bullet).strip().rstrip(".")
        if 40 <= len(line) <= 200 and not line.endswith(":"):
            lines.append(line)
    return lines[:12]


def _looks_like_heading(line: str) -> bool:
    """Project titles and dates are not continuations of the previous bullet."""
    if len(line) < 60 and (line.isupper() or line.endswith(":")):
        return True
    return bool(re.match(r"^[A-Z][\w .+-]{0,50}\s+[-|]\s+", line)) or bool(
        re.match(r"^\w{3,9}\s+(19|20)\d{2}\s*[-–]", line)
    )


# --------------------------------------------------------------------------- #
# 4. The LLM engine
# --------------------------------------------------------------------------- #

QUESTION_SYSTEM = (
    "You are an experienced technical interviewer. You write interview questions "
    "that are specific to the candidate in front of you: you quote their projects, "
    "you probe the skills they claim, and you never ask something answerable by "
    "reciting a definition when a follow-up would reveal more. Questions must be "
    "answerable out loud in under three minutes."
)


def _generate_with_llm(
    parsed_resume: dict[str, Any] | None,
    role: dict,
    company: dict,
    plan: list[str],
    difficulty: str,
) -> list[dict[str, Any]] | None:
    llm = get_llm()
    if not llm.available:
        return None

    resume_excerpt = ((parsed_resume or {}).get("raw_text") or "")[:5000]
    skills = ", ".join((parsed_resume or {}).get("skill_list") or []) or "unknown"
    counts: dict[str, int] = {}
    for category in plan:
        counts[category] = counts.get(category, 0) + 1

    prompt = (
        f"ROLE: {role['title']}\n"
        f"WHAT THIS ROLE PROBES: {', '.join(role['focus'])}\n"
        f"COMPANY STYLE: {company['name']} - {company['notes']}\n"
        f"TARGET DIFFICULTY: {difficulty}\n"
        f"CANDIDATE SKILLS DETECTED: {skills}\n"
        f"QUESTION MIX REQUIRED: "
        + ", ".join(f"{n} {category}" for category, n in counts.items())
        + "\n\nCANDIDATE RESUME:\n"
        + (resume_excerpt or "(no resume provided - ask role-generic questions)")
        + "\n\nReturn a JSON array. Each item: {\"category\": one of "
        "[technical, behavioral, situational, resume], \"skill\": string or null, "
        "\"difficulty\": one of [easy, medium, hard], \"text\": the question, "
        "\"expected_points\": [3-4 things a strong answer must contain]}. "
        "Resume-category questions must quote the resume."
    )

    data = llm.complete_json(QUESTION_SYSTEM, prompt, fallback=None, max_tokens=2500)
    if not isinstance(data, list) or not data:
        return None

    questions: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        difficulty_value = str(item.get("difficulty", difficulty)).lower()
        questions.append({
            "category": str(item.get("category", "technical")).lower(),
            "skill": item.get("skill"),
            "difficulty": difficulty_value if difficulty_value in DIFFICULTY_ORDER else difficulty,
            "text": str(item["text"]).strip(),
            "expected_points": [str(p) for p in (item.get("expected_points") or [])][:5],
            "source": "llm",
        })
    return questions or None


# --------------------------------------------------------------------------- #
# 5. Coding round
# --------------------------------------------------------------------------- #

CODING_BANK: list[dict[str, Any]] = [
    {
        "slug": "two-sum",
        "title": "Two Sum",
        "difficulty": "easy",
        "skill": "Data Structures",
        "prompt": "Given an array of integers and a target, return the indices of the two "
                  "numbers that add up to the target. Assume exactly one solution exists.",
        "examples": [{"input": "nums = [2,7,11,15], target = 9", "output": "[0,1]"}],
        "starter_code": "def two_sum(nums, target):\n    # your code here\n    pass\n",
        "expected_points": ["hash map of value -> index", "single pass", "O(n) time, O(n) space",
                            "handles duplicates"],
    },
    {
        "slug": "valid-parentheses",
        "title": "Valid Parentheses",
        "difficulty": "easy",
        "skill": "Data Structures",
        "prompt": "Given a string containing '(', ')', '{', '}', '[' and ']', decide whether "
                  "the brackets are balanced and correctly nested.",
        "examples": [{"input": '"([{}])"', "output": "true"}, {"input": '"(]"', "output": "false"}],
        "starter_code": "def is_valid(s):\n    # your code here\n    pass\n",
        "expected_points": ["stack", "map closing to opening", "empty stack at the end", "O(n)"],
    },
    {
        "slug": "group-anagrams",
        "title": "Group Anagrams",
        "difficulty": "medium",
        "skill": "Algorithms",
        "prompt": "Group a list of strings into anagram groups.",
        "examples": [{"input": '["eat","tea","tan","ate","nat","bat"]',
                      "output": '[["eat","tea","ate"],["tan","nat"],["bat"]]'}],
        "starter_code": "def group_anagrams(words):\n    # your code here\n    pass\n",
        "expected_points": ["sorted string or char-count as the key", "dict of key -> list",
                            "O(n * k log k) or O(n * k)"],
    },
    {
        "slug": "lru-cache",
        "title": "LRU Cache",
        "difficulty": "hard",
        "skill": "System Design",
        "prompt": "Design a cache with get(key) and put(key, value) in O(1), evicting the "
                  "least-recently-used entry when it exceeds capacity.",
        "examples": [{"input": "capacity=2; put(1,1); put(2,2); get(1); put(3,3)",
                      "output": "key 2 is evicted"}],
        "starter_code": "class LRUCache:\n    def __init__(self, capacity):\n        pass\n\n"
                        "    def get(self, key):\n        pass\n\n"
                        "    def put(self, key, value):\n        pass\n",
        "expected_points": ["hash map + doubly linked list", "both operations O(1)",
                            "eviction on overflow", "why OrderedDict works"],
    },
    {
        "slug": "top-k-frequent",
        "title": "Top K Frequent Elements",
        "difficulty": "medium",
        "skill": "Algorithms",
        "prompt": "Return the k most frequent elements of an array.",
        "examples": [{"input": "nums = [1,1,1,2,2,3], k = 2", "output": "[1,2]"}],
        "starter_code": "def top_k_frequent(nums, k):\n    # your code here\n    pass\n",
        "expected_points": ["count with a dict", "heap of size k or bucket sort",
                            "better than O(n log n)"],
    },
    {
        "slug": "sql-second-highest",
        "title": "Second Highest Salary (SQL)",
        "difficulty": "medium",
        "skill": "SQL",
        "prompt": "Write a query returning the second-highest salary from an Employee(id, salary) "
                  "table. Return NULL if there is no second-highest.",
        "examples": [{"input": "salaries 100, 200, 300", "output": "200"}],
        "starter_code": "-- your query here\nSELECT\n",
        "expected_points": ["DISTINCT to handle ties", "OFFSET 1 LIMIT 1 or a subquery",
                            "returns NULL rather than no row"],
    },
]


def generate_coding_problems(
    role_key: str | None = None,
    count: int = 2,
    difficulty: str = "medium",
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Pick coding problems weighted towards the role's required skills."""
    _, role = role_or_default(role_key)
    rng = random.Random(seed)
    wanted = set(role["must_have"] + role["good_to_have"])

    relevant = [p for p in CODING_BANK if p["skill"] in wanted]
    pool = relevant or list(CODING_BANK)
    preferred = [p for p in pool if p["difficulty"] == difficulty] or pool

    chosen = rng.sample(preferred, min(count, len(preferred)))
    if len(chosen) < count:
        # Top up from the WHOLE bank, not just the role-relevant slice. Some
        # roles only match one or two problems, and returning fewer problems
        # than the candidate asked for is worse than including a general one.
        remaining = [p for p in CODING_BANK if p not in chosen]
        chosen += rng.sample(remaining, min(count - len(chosen), len(remaining)))

    problems = []
    for index, problem in enumerate(chosen, start=1):
        problems.append({**problem, "index": index, "category": "coding",
                         "time_limit_sec": TIME_LIMITS["coding"], "source": "bank"})
    return problems
