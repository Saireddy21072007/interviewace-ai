"""
Pydantic request/response models.

These are the API's actual contract - the thing the frontend types itself
against and the thing FastAPI turns into the OpenAPI docs at /docs. Keeping
them separate from the SQLAlchemy models means we choose what leaves the
server: `User` has a password_hash column, `UserOut` does not, and it cannot
accidentally start returning one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

ExperienceLevel = Literal["fresher", "junior", "mid", "senior"]
Difficulty = Literal["easy", "medium", "hard"]
InterviewMode = Literal["voice", "text", "coding"]


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=120)
    target_role: str = Field(default="full-stack-developer", max_length=60)
    experience_level: ExperienceLevel = "fresher"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: str
    target_role: str
    experience_level: str
    created_at: datetime
    last_login_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserOut


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    target_role: str | None = Field(default=None, max_length=60)
    experience_level: ExperienceLevel | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# --------------------------------------------------------------------------- #
# Resumes
# --------------------------------------------------------------------------- #


class ResumeSummary(BaseModel):
    """The list view - deliberately excludes raw_text, which is huge."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    size_bytes: int
    skills: list[str] = []
    ats_score: int | None = None
    role_key: str | None = None
    is_primary: bool = False
    created_at: datetime
    analyzed_at: datetime | None = None


class ResumeDetail(ResumeSummary):
    parsed: dict[str, Any] = {}
    ats_result: dict[str, Any] = {}
    job_description: str = ""


class UploadResumeResponse(BaseModel):
    resume: ResumeDetail
    warnings: list[str] = []
    detected_skills: list[str] = []
    message: str


class AnalyzeResumeRequest(BaseModel):
    resume_id: int | None = Field(
        default=None, description="Defaults to the most recently uploaded resume.")
    role_key: str | None = None
    job_description: str = ""
    experience_level: ExperienceLevel | None = None


class AnalyzeResumeResponse(BaseModel):
    resume_id: int
    score: int
    grade: str
    band: str
    role_key: str
    role_title: str
    breakdown: list[dict[str, Any]]
    matched_skills: list[str]
    missing_must_have: list[str]
    missing_good_to_have: list[str]
    extra_skills: list[str]
    suggestions: list[str]
    review: dict[str, Any]
    warnings: list[str] = []


# --------------------------------------------------------------------------- #
# Interviews
# --------------------------------------------------------------------------- #


class GenerateQuestionsRequest(BaseModel):
    resume_id: int | None = None
    role_key: str | None = None
    company_key: str = "generic"
    mode: InterviewMode = "voice"
    difficulty: Difficulty = "medium"
    count: int = Field(default=8, ge=1, le=20)
    coding_problems: int = Field(default=0, ge=0, le=5)


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    index: int
    category: str
    skill: str | None = None
    difficulty: str
    text: str
    time_limit_sec: int
    source: str
    problem: dict[str, Any] = {}
    # expected_points is intentionally NOT exposed while the interview is
    # running - handing the candidate the mark scheme mid-question would make
    # every score meaningless. The report includes it afterwards.


class InterviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role_key: str
    company_key: str
    mode: str
    difficulty: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_sec: float = 0.0
    overall_score: int | None = None


class GenerateQuestionsResponse(BaseModel):
    interview: InterviewOut
    questions: list[QuestionOut]
    engine: str  # "llm" or "bank" - shown in the UI so the demo is honest


class SubmitAnswerRequest(BaseModel):
    """Used for typed answers and for the coding round.

    Spoken answers go to the multipart endpoint POST /submit-answer/audio,
    because a 2MB audio blob does not belong in a JSON body.
    """
    question_id: int
    transcript: str = ""
    duration_sec: float | None = None
    code: str = ""
    language: str = "python"
    evaluate_now: bool = True


class AnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_id: int
    transcript: str
    transcript_source: str
    duration_sec: float | None = None
    code: str = ""
    language: str = "python"
    overall_score: int | None = None
    scores: dict[str, Any] = {}
    evaluation: dict[str, Any] = {}
    created_at: datetime


class SubmitAnswerResponse(BaseModel):
    answer: AnswerOut
    transcription: dict[str, Any] = {}
    next_question: QuestionOut | None = None
    answered: int
    total: int


class EvaluateRequest(BaseModel):
    """POST /evaluate - score an interview, or re-score one answer."""
    interview_id: int | None = None
    answer_id: int | None = None
    finalise: bool = True


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #


class ReportQuestionDetail(BaseModel):
    index: int
    category: str
    skill: str | None
    difficulty: str
    question: str
    expected_points: list[str]
    transcript: str
    code: str = ""
    duration_sec: float | None = None
    overall_score: int | None
    scores: dict[str, Any] = {}
    evaluation: dict[str, Any] = {}


class ReportOut(BaseModel):
    interview: InterviewOut
    overall_score: int
    verdict: str
    headline: str = ""
    dimension_averages: dict[str, float] = {}
    by_category: dict[str, int] = {}
    strengths: list[str] = []
    improvements: list[str] = []
    answered: int = 0
    total: int = 0
    questions: list[ReportQuestionDetail] = []
    created_at: datetime | None = None


# --------------------------------------------------------------------------- #
# Roadmap
# --------------------------------------------------------------------------- #


class RoadmapRequest(BaseModel):
    resume_id: int | None = None
    interview_id: int | None = None
    role_key: str | None = None
    weeks: int = Field(default=8, ge=2, le=24)
    hours_per_week: int = Field(default=8, ge=2, le=40)


class RoadmapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role_key: str
    week_count: int
    hours_per_week: int
    total_hours: int
    coach_note: str
    weeks: list[dict[str, Any]]
    gaps: list[dict[str, Any]]
    progress: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime


class RoadmapProgressUpdate(BaseModel):
    task_key: str = Field(description="'<week>-<taskIndex>', e.g. '2-0'")
    done: bool


# --------------------------------------------------------------------------- #
# Dashboard + admin
# --------------------------------------------------------------------------- #


class DashboardStats(BaseModel):
    resumes: int
    interviews_started: int
    interviews_completed: int
    questions_answered: int
    best_ats_score: int | None
    latest_ats_score: int | None
    average_interview_score: int | None
    best_interview_score: int | None
    practice_minutes: int
    score_trend: list[dict[str, Any]] = []
    weakest_dimension: str | None = None
    strongest_dimension: str | None = None
    recent_interviews: list[InterviewOut] = []
    latest_resume: ResumeSummary | None = None
    has_roadmap: bool = False


class AdminUserRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: str
    target_role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None
    resume_count: int = 0
    interview_count: int = 0


class AdminStats(BaseModel):
    users: int
    active_users_7d: int
    resumes: int
    interviews: int
    completed_interviews: int
    answers: int
    average_ats_score: float | None
    average_interview_score: float | None
    llm: dict[str, Any]
    stt: dict[str, Any]
    database: str
    warnings: list[str] = []
