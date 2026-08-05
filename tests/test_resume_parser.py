"""Resume parsing: contact extraction, sections, skills, experience, signals."""

from __future__ import annotations

from ai.resume_parser import (
    detect_skills, estimate_experience_years, extract_contact, parse_resume,
    split_sections, writing_signals,
)


def test_parses_a_normal_resume(sample_resume_bytes):
    parsed = parse_resume(sample_resume_bytes, "sample_resume.txt")

    assert parsed["ok"] is True
    assert parsed["contact"]["name"] == "Ananya Sharma"
    assert parsed["contact"]["email"] == "ananya.sharma@example.com"
    assert "98765" in (parsed["contact"]["phone"] or "")
    assert "github.com/ananyasharma" in (parsed["contact"]["github"] or "")


def test_finds_every_expected_section(sample_resume_bytes):
    parsed = parse_resume(sample_resume_bytes, "sample_resume.txt")
    for section in ("education", "experience", "projects", "skills", "certifications"):
        assert section in parsed["section_names"], f"missing section: {section}"


def test_detects_canonical_skills_not_surface_forms(sample_resume_text):
    skills = detect_skills(sample_resume_text)

    # "React", "FastAPI" and "PostgreSQL" appear literally.
    for expected in ("React", "FastAPI", "PostgreSQL", "TypeScript", "Docker"):
        assert expected in skills

    # These are inferred from aliases, which is the point of the alias table:
    # "JWT authentication" -> Authentication, "Celery" -> Message Queues.
    assert "Authentication" in skills
    assert "Message Queues" in skills
    assert "CI/CD" in skills  # from "GitHub Actions"


def test_cpp_does_not_register_as_c():
    """'C++' must not also count as the language 'C'.

    Regression test: the word-boundary class has to include '+' and '#',
    otherwise every C++ developer silently gets credit for C as well.
    """
    skills = detect_skills("Languages: Python, C++, JavaScript")
    assert "C++" in skills
    assert "C" not in skills


def test_short_ambiguous_aliases_need_the_right_casing():
    """'go to market' is not Golang; 'R' the language is written capitalised."""
    assert "Go" not in detect_skills("We had to go to market quickly")
    assert "R" in detect_skills("Statistical analysis in R and Python")


def test_experience_is_counted_in_months_not_whole_years():
    """A summer internship is real experience worth ~0.2 years, not zero."""
    sections = {"experience": "Software Intern, Acme\nMay 2025 - Jul 2025\n- Built things."}
    years = estimate_experience_years("", sections)
    assert 0.1 <= years <= 0.3


def test_overlapping_roles_are_not_double_counted():
    sections = {"experience": (
        "Backend Intern, Alpha\nJan 2024 - Dec 2024\n"
        "Research Assistant, Beta\nMar 2024 - Dec 2024\n"
    )}
    assert estimate_experience_years("", sections) <= 1.1


def test_education_dates_do_not_become_work_experience(sample_resume_bytes):
    """The resume has a 2022-2026 degree. That is not four years of work."""
    parsed = parse_resume(sample_resume_bytes, "sample_resume.txt")
    assert parsed["experience_years"] < 1.0


def test_writing_signals_spot_impact_and_filler():
    strong = writing_signals("- Reduced latency from 480ms to 120ms\n- Built 12 APIs")
    weak = writing_signals("Responsible for various tasks. Worked on the backend.")

    assert strong["quantified_results"] >= 2
    assert "built" in strong["action_verbs"]
    assert "responsible for" in weak["weak_phrases"]
    assert weak["quantified_results"] == 0


def test_unsupported_file_type_is_reported_not_raised():
    parsed = parse_resume(b"binary junk", "resume.pages")
    assert parsed["ok"] is False
    assert parsed["warnings"]
    assert "Unsupported" in parsed["warnings"][0]


def test_empty_input_never_raises():
    parsed = parse_resume(b"", "resume.txt")
    assert parsed["ok"] is False
    assert parsed["skill_list"] == []


def test_headings_are_matched_but_sentences_are_not():
    text = "SKILLS\nPython\n\nMy experience with education systems is broad.\nEDUCATION\nB.Tech"
    sections = split_sections(text)
    assert "skills" in sections
    assert "education" in sections
    assert "broad" in sections["skills"]  # the sentence stayed in the previous section


def test_contact_prefers_the_header_block():
    text = "Ravi Kumar\n+91 90000 11111\nravi@example.com\n\nProjects\nCalled 1800 200 3000 support."
    contact = extract_contact(text)
    assert contact["phone"].strip().startswith("+91")
