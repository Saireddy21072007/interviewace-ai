"""
Reference data and the dashboard.

    GET /health      is the system up, and which AI engines are live
    GET /roles       the role taxonomy, for the setup dropdowns
    GET /companies   interview style profiles
    GET /dashboard   everything the dashboard page needs, in one call

/dashboard is one endpoint rather than six because the dashboard would
otherwise fire six requests on every page load and render in six stages.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from ai.llm import get_llm
from ai.skills_db import ALL_SKILLS, COMPANIES, ROLES
from ai.stt import describe as describe_stt

from ..config import get_settings
from ..deps import CurrentUser, DbSession
from ..models import Answer, Interview, Resume, Roadmap, utcnow
from ..schemas import DashboardStats, InterviewOut, ResumeSummary

router = APIRouter(tags=["meta"])
settings = get_settings()


@router.get("/health")
def health() -> dict:
    """Open endpoint - used by the frontend banner and by uptime checks.

    It reports which engines are live so a demo never silently runs on
    fallbacks while everyone assumes the LLM is answering.
    """
    llm = get_llm()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "llm": llm.describe(),
        "stt": describe_stt(),
        "database": "postgresql" if settings.database_url.startswith("postgres") else "sqlite",
    }


@router.get("/roles")
def list_roles() -> dict:
    return {
        "roles": [
            {
                "key": key,
                "title": spec["title"],
                "family": spec["family"],
                "must_have": spec["must_have"],
                "good_to_have": spec["good_to_have"],
                "focus": spec["focus"],
            }
            for key, spec in ROLES.items()
        ],
        "skills": ALL_SKILLS,
        "experience_levels": ["fresher", "junior", "mid", "senior"],
    }


@router.get("/companies")
def list_companies() -> dict:
    return {
        "companies": [
            {"key": key, "name": spec["name"], "notes": spec["notes"], "mix": spec["mix"]}
            for key, spec in COMPANIES.items()
        ]
    }


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(user: CurrentUser, db: DbSession) -> DashboardStats:
    resume_count = db.scalar(select(func.count(Resume.id)).where(Resume.user_id == user.id)) or 0
    latest_resume = db.scalar(
        select(Resume).where(Resume.user_id == user.id)
        .order_by(Resume.is_primary.desc(), Resume.created_at.desc())
    )
    best_ats = db.scalar(select(func.max(Resume.ats_score)).where(Resume.user_id == user.id))

    interviews = list(db.scalars(
        select(Interview).where(Interview.user_id == user.id)
        .order_by(Interview.started_at.desc())
    ))
    completed = [i for i in interviews if i.status == "completed" and i.overall_score is not None]

    answers_count = db.scalar(
        select(func.count(Answer.id)).join(Interview).where(Interview.user_id == user.id)
    ) or 0
    total_seconds = db.scalar(
        select(func.coalesce(func.sum(Interview.duration_sec), 0.0))
        .where(Interview.user_id == user.id)
    ) or 0.0

    # Score trend runs oldest -> newest so the chart reads left to right.
    trend = [
        {
            "interview_id": i.id,
            "date": (i.completed_at or i.started_at).isoformat(),
            "score": i.overall_score,
            "role": i.role_key,
        }
        for i in reversed(completed[:10])
    ]

    strongest = weakest = None
    if completed:
        latest_report = completed[0].report
        summary = (latest_report.summary if latest_report else {}) or {}
        strongest = summary.get("strongest_dimension")
        weakest = summary.get("weakest_dimension")

    has_roadmap = bool(db.scalar(
        select(func.count(Roadmap.id)).where(Roadmap.user_id == user.id)))

    return DashboardStats(
        resumes=resume_count,
        interviews_started=len(interviews),
        interviews_completed=len(completed),
        questions_answered=answers_count,
        best_ats_score=best_ats,
        latest_ats_score=latest_resume.ats_score if latest_resume else None,
        average_interview_score=(
            round(sum(i.overall_score for i in completed) / len(completed)) if completed else None
        ),
        best_interview_score=max((i.overall_score for i in completed), default=None),
        practice_minutes=int(total_seconds // 60),
        score_trend=trend,
        strongest_dimension=strongest,
        weakest_dimension=weakest,
        recent_interviews=[InterviewOut.model_validate(i) for i in interviews[:5]],
        latest_resume=ResumeSummary.model_validate(latest_resume) if latest_resume else None,
        has_roadmap=has_roadmap,
    )


def _seven_days_ago():
    return utcnow() - timedelta(days=7)
