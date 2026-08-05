"""
InterviewAce AI - the intelligence layer.

This package is deliberately free of any web-framework imports. Every module
here is plain Python that takes data in and returns data out, which means:

  * the CSE-AI team can develop and test it without running the backend,
  * the backend can call it like a library,
  * and swapping a model or provider never touches API code.

Modules
-------
llm.py            The ONLY file that talks to an LLM provider.
stt.py            The ONLY file that turns audio into text.
resume_parser.py  PDF/DOCX/TXT -> structured resume dict.
skills_db.py      Role -> required-skill taxonomy + learning resources.
ats.py            Resume + role -> ATS score with explainable sub-scores.
question_gen.py   Resume + role -> interview questions.
evaluator.py      Question + answer -> rubric scores + feedback.
recommender.py    Skill gap -> personalised weekly learning roadmap.
"""

__version__ = "1.0.0"
