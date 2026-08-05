"""
Resume -> structured data.

Input : a PDF, DOCX or TXT file (bytes or path)
Output: a dict with contact details, sections, detected skills, experience
        estimate and writing-quality signals.

DESIGN NOTES
------------
* Parsing is rule-based, not model-based. An ATS is rule-based, so if we want
  the score to predict what a real ATS does, we have to fail the same way one
  does. A resume that a regex cannot read is a resume the recruiter's software
  cannot read either - that is signal, not a bug.
* Nothing here raises on malformed input. A resume that cannot be parsed
  returns a mostly-empty dict with `warnings` filled in, and the UI shows those
  warnings to the candidate. Crashing the upload endpoint is not an option.
* `spacy` is deliberately optional. It improves NAME and ORGANISATION
  detection, and we use it when installed, but the project must install and run
  from a plain `pip install -r requirements.txt`.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from .skills_db import ALIAS_TO_SKILL, SOFT_SKILLS

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

# --------------------------------------------------------------------------- #
# Text extraction
# --------------------------------------------------------------------------- #


def extract_text(source: str | Path | bytes, filename: str | None = None) -> tuple[str, list[str]]:
    """Return (text, warnings) for a resume file.

    `source` may be a path or raw bytes. When passing bytes, also pass
    `filename` so we know which reader to use.
    """
    warnings: list[str] = []

    if isinstance(source, (str, Path)):
        path = Path(source)
        suffix = path.suffix.lower()
        data = path.read_bytes()
    else:
        data = source
        suffix = Path(filename or "").suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        return "", [f"Unsupported file type '{suffix or 'unknown'}'. Upload a PDF, DOCX or TXT."]

    try:
        if suffix == ".pdf":
            text = _read_pdf(data)
            if len(text.strip()) < 40:
                warnings.append(
                    "Almost no text could be read from this PDF. It is probably a scanned "
                    "image - most ATS software will score it 0. Export a text-based PDF."
                )
        elif suffix == ".docx":
            text = _read_docx(data)
        else:
            text = data.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - never let a bad file 500 the API
        log.warning("resume extraction failed: %s", exc)
        return "", [f"Could not read the file: {exc}"]

    return _normalise(text), warnings


def _read_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(data: bytes) -> str:
    import docx  # python-docx

    document = docx.Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs]
    # Many resume templates put half the content in tables.
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


def _normalise(text: str) -> str:
    """Tidy whitespace and the bullet characters PDF extraction leaves behind."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[•●▪‣⁃]", "- ", text)
    text = re.sub(r"[–—]", "-", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------- #
# Contact details
# --------------------------------------------------------------------------- #

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
# Any run of digits/separators that could be a phone number. We validate the
# digit count afterwards rather than trying to encode every national format -
# resumes write "+91 98765 43210", "(080) 4567-8901" and "9876543210" alike.
PHONE_RE = re.compile(r"(?:\+|00)?[\d][\d\s().-]{7,17}\d")
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w%-]+", re.I)
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w-]+", re.I)
URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)


def extract_contact(text: str) -> dict[str, Any]:
    """Pull email, phone, profile links and a best guess at the name."""
    email = EMAIL_RE.search(text)
    # Search the header block first so a date range or an ID later in the
    # document cannot beat the real phone number.
    header = "\n".join(text.splitlines()[:12])
    phone = _first_phone(header) or _first_phone(text)
    linkedin = LINKEDIN_RE.search(text)
    github = GITHUB_RE.search(text)

    return {
        "name": _guess_name(text),
        "email": email.group(0) if email else None,
        "phone": phone,
        "linkedin": linkedin.group(0) if linkedin else None,
        "github": github.group(0) if github else None,
        "links": sorted(set(URL_RE.findall(text)))[:8],
    }


def _first_phone(text: str) -> str | None:
    """First match with a plausible number of digits (10-13 covers India + intl)."""
    for match in PHONE_RE.finditer(text):
        candidate = match.group(0).strip()
        digits = re.sub(r"\D", "", candidate)
        if 10 <= len(digits) <= 13:
            return candidate
    return None


_NAME_STOPWORDS = {
    "resume", "curriculum", "vitae", "cv", "profile", "summary", "objective",
    "contact", "phone", "email", "address", "linkedin", "github", "portfolio",
}


def _guess_name(text: str) -> str | None:
    """The candidate's name is almost always the first real line of a resume.

    We take the first line that looks like 1-4 capitalised words and contains
    no digits or '@'. If spaCy is installed we ask it for a PERSON entity in
    the header block first, because that handles single-word and all-caps names
    better.
    """
    header = "\n".join(text.splitlines()[:8])

    try:  # optional, better accuracy when present
        nlp = _load_spacy()
        if nlp is not None:
            doc = nlp(header)
            for ent in doc.ents:
                if ent.label_ == "PERSON" and 2 <= len(ent.text) <= 60:
                    return ent.text.strip()
    except Exception:  # noqa: BLE001 - spaCy is a nice-to-have
        pass

    for line in text.splitlines()[:8]:
        candidate = line.strip().strip("|-,")
        if not (2 <= len(candidate) <= 60):
            continue
        if any(ch.isdigit() for ch in candidate) or "@" in candidate or "http" in candidate.lower():
            continue
        words = candidate.split()
        if not (1 <= len(words) <= 4):
            continue
        if any(w.lower().strip(":") in _NAME_STOPWORDS for w in words):
            continue
        if all(w[0].isupper() for w in words if w):
            return candidate
    return None


_SPACY_NLP: Any = None
_SPACY_TRIED = False


def _load_spacy() -> Any:
    global _SPACY_NLP, _SPACY_TRIED
    if _SPACY_TRIED:
        return _SPACY_NLP
    _SPACY_TRIED = True
    try:
        import spacy  # type: ignore

        _SPACY_NLP = spacy.load("en_core_web_sm")
    except Exception:  # noqa: BLE001
        _SPACY_NLP = None
    return _SPACY_NLP


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #

SECTION_PATTERNS: dict[str, list[str]] = {
    "summary": ["summary", "objective", "profile", "about me", "career objective"],
    "education": ["education", "academic", "academics", "qualification", "qualifications"],
    "experience": ["experience", "work experience", "employment", "professional experience",
                   "internship", "internships", "work history"],
    "projects": ["projects", "personal projects", "academic projects", "key projects"],
    "skills": ["skills", "technical skills", "technologies", "tech stack", "core competencies"],
    "certifications": ["certifications", "certificates", "courses", "licenses"],
    "achievements": ["achievements", "awards", "honors", "honours", "accomplishments",
                     "extracurricular", "activities", "publications"],
}

_HEADING_LOOKUP = {
    alias: canonical
    for canonical, aliases in SECTION_PATTERNS.items()
    for alias in aliases
}


def split_sections(text: str) -> dict[str, str]:
    """Split resume text into canonical sections keyed by SECTION_PATTERNS.

    A line is treated as a heading when, after stripping punctuation, it
    matches a known heading alias and is short (headings are never sentences).
    """
    sections: dict[str, list[str]] = {}
    current = "header"
    sections[current] = []

    for line in text.splitlines():
        stripped = line.strip()
        key = _heading_key(stripped)
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)

    return {name: "\n".join(lines).strip() for name, lines in sections.items() if lines}


def _heading_key(line: str) -> str | None:
    if not line or len(line) > 45:
        return None
    cleaned = re.sub(r"[^a-z ]", " ", line.lower()).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return None
    return _HEADING_LOOKUP.get(cleaned)


# --------------------------------------------------------------------------- #
# Skill detection
# --------------------------------------------------------------------------- #

# Aliases this short are only trusted when they appear in the exact casing the
# industry uses ("R", "ML", "Go"), otherwise "go to market" becomes Golang.
_CASE_SENSITIVE_ALIASES = {
    alias for alias in ALIAS_TO_SKILL if len(alias) <= 2
} | {"go", "ml", "tf", "js", "ts", "py", "os", "ai", "rag", "nlp", "cv"}


def detect_skills(text: str) -> dict[str, list[str]]:
    """Find canonical skills in the text.

    Returns {skill: [matched surface forms]} so the UI can show the candidate
    exactly which words earned each skill - that is what makes the ATS score
    arguable instead of magic.
    """
    found: dict[str, list[str]] = {}
    lowered = text.lower()

    for alias, canonical in ALIAS_TO_SKILL.items():
        if alias in _CASE_SENSITIVE_ALIASES:
            # '+' and '#' must be in the boundary class, otherwise the "C" in
            # "C++" and the "C" in "C#" both register as plain C.
            pattern = re.compile(rf"(?<![A-Za-z0-9+#]){re.escape(alias.upper())}(?![A-Za-z0-9+#])")
            hit = pattern.search(text) or re.search(
                rf"(?<![A-Za-z0-9+#]){re.escape(alias.capitalize())}(?![A-Za-z0-9+#])", text
            )
            if not hit:
                continue
            matched = hit.group(0)
        else:
            if alias not in lowered:  # cheap pre-filter before the regex
                continue
            pattern = re.compile(rf"(?<![A-Za-z0-9+#]){re.escape(alias)}(?![A-Za-z0-9+#])", re.I)
            hit = pattern.search(text)
            if not hit:
                continue
            matched = hit.group(0)

        found.setdefault(canonical, [])
        if matched.lower() not in {m.lower() for m in found[canonical]}:
            found[canonical].append(matched)

    return dict(sorted(found.items()))


# --------------------------------------------------------------------------- #
# Experience estimate + writing quality signals
# --------------------------------------------------------------------------- #

YEAR_RE = re.compile(r"(19|20)\d{2}")
DATE_RANGE_RE = re.compile(
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*)?((?:19|20)\d{2})"
    r"\s*(?:-|to|until|–)\s*"
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*)?((?:19|20)\d{2}|present|current|now)",
    re.I,
)

ACTION_VERBS = {
    "built", "designed", "developed", "implemented", "led", "created", "improved",
    "reduced", "increased", "automated", "optimised", "optimized", "launched",
    "migrated", "deployed", "architected", "shipped", "owned", "mentored",
    "analysed", "analyzed", "integrated", "refactored", "scaled", "delivered",
}

WEAK_PHRASES = {
    "responsible for", "worked on", "helped with", "involved in", "duties included",
    "familiar with", "exposure to", "assisted in",
}

METRIC_RE = re.compile(r"(\d+(?:\.\d+)?\s*%|\b\d{2,}\s*(?:x|times|users|ms|s\b|k\b|lakh|crore)|\$\s?\d|₹\s?\d)", re.I)


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def estimate_experience_years(text: str, sections: dict[str, str]) -> float:
    """Estimate total professional experience from date ranges.

    Works in MONTHS, not years: a summer internship ("May 2025 - Jul 2025") is
    real experience worth 0.2 years, and rounding it to zero would under-score
    every student this product is built for.

    Only the experience section is scanned, so a 2022-2026 degree is not read
    as four years of work. Overlapping ranges are merged - two parallel
    internships are not two years of experience.
    """
    scope = sections.get("experience", "") or text
    today = date.today()
    now_index = today.year * 12 + today.month
    intervals: list[tuple[int, int]] = []

    for match in DATE_RANGE_RE.finditer(scope):
        start_month = MONTHS.get((match.group(1) or "")[:3].lower(), 1)
        start = int(match.group(2)) * 12 + start_month

        end_raw = match.group(4)
        if end_raw.isdigit():
            end_month = MONTHS.get((match.group(3) or "")[:3].lower(), 12)
            end = int(end_raw) * 12 + end_month
        else:  # "present" / "current" / "now"
            end = now_index

        if start <= end <= now_index + 1 and start > 1980 * 12:
            intervals.append((start, min(end, now_index)))

    if not intervals:
        return 0.0

    intervals.sort()
    merged: list[list[int]] = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    months = sum(end - start for start, end in merged)
    return round(months / 12.0, 1)


def writing_signals(text: str) -> dict[str, Any]:
    """Quality signals an ATS and a recruiter both react to."""
    words = re.findall(r"[A-Za-z']+", text)
    bullets = [ln for ln in text.splitlines() if ln.strip().startswith(("-", "*", "•"))]
    lowered = text.lower()

    return {
        "word_count": len(words),
        "bullet_count": len(bullets),
        "action_verbs": sorted({w.lower() for w in words if w.lower() in ACTION_VERBS}),
        "weak_phrases": sorted({p for p in WEAK_PHRASES if p in lowered}),
        "quantified_results": len(METRIC_RE.findall(text)),
        "estimated_pages": max(1, round(len(words) / 500)),
    }


# --------------------------------------------------------------------------- #
# The one function the backend calls
# --------------------------------------------------------------------------- #


def parse_resume(source: str | Path | bytes, filename: str | None = None) -> dict[str, Any]:
    """Full pipeline: bytes/path in, structured resume dict out. Never raises."""
    text, warnings = extract_text(source, filename)

    if not text:
        return {
            "ok": False,
            "warnings": warnings or ["The file appeared to be empty."],
            "raw_text": "",
            "contact": {"name": None, "email": None, "phone": None,
                        "linkedin": None, "github": None, "links": []},
            "sections": {},
            "skills": {},
            "skill_list": [],
            "soft_skills": [],
            "experience_years": 0.0,
            "signals": writing_signals(""),
        }

    sections = split_sections(text)
    skills = detect_skills(text)
    skill_list = sorted(skills)

    if "skills" not in sections:
        warnings.append(
            "No 'Skills' heading found. Most ATS parsers look for one - add a "
            "clearly-labelled Skills section."
        )
    if "education" not in sections:
        warnings.append("No 'Education' heading found.")

    return {
        "ok": True,
        "warnings": warnings,
        "raw_text": text,
        "contact": extract_contact(text),
        "sections": sections,
        "section_names": sorted(sections),
        "skills": skills,
        "skill_list": skill_list,
        "soft_skills": sorted(set(skill_list) & SOFT_SKILLS),
        "experience_years": estimate_experience_years(text, sections),
        "signals": writing_signals(text),
    }
