"""
Admin dashboard (module 10 in the project guide).

Everything here requires `role == "admin"`, which is granted only to the
address in ADMIN_EMAIL at registration time. There is deliberately no
"promote to admin" endpoint: the fastest way to lose a platform is to ship a
privilege-escalation path in a student project.

Note what admins can and cannot see. They get counts, scores and account
status - the operational picture. They do not get resume text, transcripts or
audio. Those belong to the candidate, and no product requirement here needs
them to be readable by staff.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from ai.llm import get_llm
from ai.stt import describe as describe_stt

from ..config import get_settings
from ..deps import AdminUser, DbSession
from ..models import Answer, Interview, Resume, User, utcnow
from ..schemas import AdminStats, AdminUserRow

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


@router.get("/stats", response_model=AdminStats)
def stats(_: AdminUser, db: DbSession) -> AdminStats:
    seven_days_ago = utcnow() - timedelta(days=7)

    warnings: list[str] = []
    if settings.is_insecure_secret():
        warnings.append(
            "SECRET_KEY is still the default value. Every issued token can be forged. "
            "Set a real one in .env before deploying."
        )
    llm = get_llm()
    if not llm.available:
        warnings.append(
            "No LLM API key configured - questions and feedback are coming from the "
            "offline template engine."
        )
    if describe_stt()["effective"] == "none":
        warnings.append(
            "No server-side speech-to-text available. Voice answers rely on the "
            "browser's Web Speech API, which only works in Chrome and Edge."
        )

    return AdminStats(
        users=db.scalar(select(func.count(User.id))) or 0,
        active_users_7d=db.scalar(
            select(func.count(User.id)).where(User.last_login_at >= seven_days_ago)) or 0,
        resumes=db.scalar(select(func.count(Resume.id))) or 0,
        interviews=db.scalar(select(func.count(Interview.id))) or 0,
        completed_interviews=db.scalar(
            select(func.count(Interview.id)).where(Interview.status == "completed")) or 0,
        answers=db.scalar(select(func.count(Answer.id))) or 0,
        average_ats_score=_rounded(db.scalar(select(func.avg(Resume.ats_score)))),
        average_interview_score=_rounded(db.scalar(select(func.avg(Interview.overall_score)))),
        llm=llm.describe(),
        stt=describe_stt(),
        database="postgresql" if settings.database_url.startswith("postgres") else "sqlite",
        warnings=warnings,
    )


@router.get("/users", response_model=list[AdminUserRow])
def list_users(_: AdminUser, db: DbSession, limit: int = 100) -> list[AdminUserRow]:
    resume_counts = dict(db.execute(
        select(Resume.user_id, func.count(Resume.id)).group_by(Resume.user_id)).all())
    interview_counts = dict(db.execute(
        select(Interview.user_id, func.count(Interview.id)).group_by(Interview.user_id)).all())

    users = db.scalars(
        select(User).order_by(User.created_at.desc()).limit(max(1, min(limit, 500))))

    return [
        AdminUserRow(
            **{field: getattr(user, field) for field in
               ("id", "email", "full_name", "role", "target_role", "is_active",
                "created_at", "last_login_at")},
            resume_count=resume_counts.get(user.id, 0),
            interview_count=interview_counts.get(user.id, 0),
        )
        for user in users
    ]


@router.patch("/users/{user_id}/active", response_model=AdminUserRow)
def set_active(user_id: int, active: bool, admin: AdminUser, db: DbSession) -> AdminUserRow:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="You cannot disable your own admin account.")

    user.is_active = active
    db.commit()
    db.refresh(user)
    return AdminUserRow(
        **{field: getattr(user, field) for field in
           ("id", "email", "full_name", "role", "target_role", "is_active",
            "created_at", "last_login_at")}
    )


def _rounded(value) -> float | None:
    return round(float(value), 1) if value is not None else None
