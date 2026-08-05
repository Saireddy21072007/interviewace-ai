"""
The seven tables from the project guide, as SQLAlchemy models.

    Users -> Resumes -> Interviews -> Questions -> Answers
                            |
                            +--> Reports
    Users -> Roadmaps

Design notes worth defending in a viva:

* Analysis output (parsed resume, ATS breakdown, rubric scores) is stored as
  JSON, not as columns. Those structures are owned by the `ai/` package and
  will change every time the model improves; a schema migration per tweak
  would make the AI team's iteration speed depend on the database team's.
  The values we query or sort by - ats_score, overall_score - ARE columns.
* Scores are duplicated between the JSON blob and their own column on purpose.
  The column is the query surface; the blob is the audit trail.
* Deletes cascade from the user down. When a candidate deletes their account,
  every transcript and audio file reference goes with it - that is a privacy
  requirement for a product that records people speaking, not a nicety.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Timezone-aware UTC. Naive datetimes are how you end up with a report
    that says an interview finished before it started."""
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(20), default="user")  # user | admin
    target_role: Mapped[str] = mapped_column(String(60), default="full-stack-developer")
    experience_level: Mapped[str] = mapped_column(String(20), default="fresher")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Resume.created_at.desc()")
    interviews: Mapped[list["Interview"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Interview.started_at.desc()")
    roadmaps: Mapped[list["Roadmap"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Roadmap.created_at.desc()")

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)

    raw_text: Mapped[str] = mapped_column(Text, default="")
    parsed: Mapped[dict] = mapped_column(JSON, default=dict)     # resume_parser output
    skills: Mapped[list] = mapped_column(JSON, default=list)     # canonical skill names

    # Latest analysis, so the dashboard does not have to re-run scoring.
    role_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    job_description: Mapped[str] = mapped_column(Text, default="")
    ats_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ats_result: Mapped[dict] = mapped_column(JSON, default=dict)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="resumes")
    interviews: Mapped[list["Interview"]] = relationship(back_populates="resume")


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)

    role_key: Mapped[str] = mapped_column(String(60), default="full-stack-developer")
    company_key: Mapped[str] = mapped_column(String(60), default="generic")
    mode: Mapped[str] = mapped_column(String(20), default="voice")   # voice | text | coding
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="in_progress", index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped[User] = relationship(back_populates="interviews")
    resume: Mapped[Resume | None] = relationship(back_populates="interviews")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan", order_by="Question.index")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan")
    report: Mapped["Report | None"] = relationship(
        back_populates="interview", cascade="all, delete-orphan", uselist=False)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True, nullable=False)

    index: Mapped[int] = mapped_column(Integer, default=1)
    category: Mapped[str] = mapped_column(String(30), default="technical")
    skill: Mapped[str | None] = mapped_column(String(60), nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_points: Mapped[list] = mapped_column(JSON, default=list)
    time_limit_sec: Mapped[int] = mapped_column(Integer, default=180)
    source: Mapped[str] = mapped_column(String(20), default="bank")  # bank | llm

    # Coding-round questions carry the problem definition with them.
    problem: Mapped[dict] = mapped_column(JSON, default=dict)

    interview: Mapped[Interview] = relationship(back_populates="questions")
    answer: Mapped["Answer | None"] = relationship(
        back_populates="question", cascade="all, delete-orphan", uselist=False)

    __table_args__ = (UniqueConstraint("interview_id", "index", name="uq_question_per_interview"),)


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True, nullable=False)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), unique=True, nullable=False)

    transcript: Mapped[str] = mapped_column(Text, default="")
    transcript_source: Mapped[str] = mapped_column(String(30), default="typed")
    audio_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Coding round
    code: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(20), default="python")

    # Evaluation
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)      # the five rubric dimensions
    evaluation: Mapped[dict] = mapped_column(JSON, default=dict)  # full evaluator output
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    interview: Mapped[Interview] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship(back_populates="answer")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    overall_score: Mapped[int] = mapped_column(Integer, default=0)
    verdict: Mapped[str] = mapped_column(String(120), default="")
    dimension_averages: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    strengths: Mapped[list] = mapped_column(JSON, default=list)
    improvements: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    interview: Mapped[Interview] = relationship(back_populates="report")


class Roadmap(Base):
    __tablename__ = "roadmaps"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    interview_id: Mapped[int | None] = mapped_column(
        ForeignKey("interviews.id", ondelete="SET NULL"), nullable=True)

    role_key: Mapped[str] = mapped_column(String(60), default="full-stack-developer")
    week_count: Mapped[int] = mapped_column(Integer, default=8)
    hours_per_week: Mapped[int] = mapped_column(Integer, default=8)
    total_hours: Mapped[int] = mapped_column(Integer, default=0)
    coach_note: Mapped[str] = mapped_column(Text, default="")

    weeks: Mapped[list] = mapped_column(JSON, default=list)
    gaps: Mapped[list] = mapped_column(JSON, default=list)
    # {"<week>-<task index>": true} - which tasks the candidate has ticked off.
    progress: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="roadmaps")


# Composite indexes for the two queries the dashboard runs on every page load.
Index("ix_interviews_user_status", Interview.user_id, Interview.status)
Index("ix_resumes_user_created", Resume.user_id, Resume.created_at)
