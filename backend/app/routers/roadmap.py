"""
GET /roadmap and POST /roadmap - the personalised learning plan.

GET returns the saved roadmap, generating one on first request if the user has
an analysed resume. POST regenerates with different parameters (more weeks,
fewer hours) and replaces the saved one.

PATCH /roadmap/{id}/progress ticks a task off. Progress is stored server-side
rather than in the browser because a study plan the user loses when they clear
their cache is a study plan they stop trusting.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ai.recommender import build_roadmap

from ..deps import CurrentUser, DbSession
from ..models import Interview, Resume, Roadmap, utcnow
from ..schemas import RoadmapOut, RoadmapProgressUpdate, RoadmapRequest

router = APIRouter(tags=["roadmap"])


@router.get("/roadmap", response_model=RoadmapOut)
def get_roadmap(user: CurrentUser, db: DbSession) -> Roadmap:
    existing = db.scalar(
        select(Roadmap).where(Roadmap.user_id == user.id).order_by(Roadmap.created_at.desc())
    )
    if existing is not None:
        return existing
    return _generate(RoadmapRequest(), user, db)


@router.post("/roadmap", response_model=RoadmapOut, status_code=status.HTTP_201_CREATED)
def create_roadmap(payload: RoadmapRequest, user: CurrentUser, db: DbSession) -> Roadmap:
    return _generate(payload, user, db)


@router.patch("/roadmap/{roadmap_id}/progress", response_model=RoadmapOut)
def update_progress(
    roadmap_id: int,
    payload: RoadmapProgressUpdate,
    user: CurrentUser,
    db: DbSession,
) -> Roadmap:
    roadmap = db.scalar(select(Roadmap).where(
        Roadmap.id == roadmap_id, Roadmap.user_id == user.id))
    if roadmap is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Roadmap not found.")

    progress = dict(roadmap.progress or {})
    if payload.done:
        progress[payload.task_key] = True
    else:
        progress.pop(payload.task_key, None)

    # JSON columns are only marked dirty on reassignment, not on mutation.
    roadmap.progress = progress
    roadmap.updated_at = utcnow()
    db.commit()
    db.refresh(roadmap)
    return roadmap


# --------------------------------------------------------------------------- #


def _generate(payload: RoadmapRequest, user, db) -> Roadmap:
    resume = _pick_resume(db, user.id, payload.resume_id)
    if resume is None or not resume.ats_result:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Analyse a resume first - the roadmap is built from your skill gaps.",
        )

    interview_summary = None
    interview_id = payload.interview_id
    interview_query = select(Interview).where(
        Interview.user_id == user.id, Interview.status == "completed")
    interview = (
        db.scalar(interview_query.where(Interview.id == interview_id))
        if interview_id is not None
        else db.scalar(interview_query.order_by(Interview.completed_at.desc()))
    )
    if interview is not None and interview.report is not None:
        interview_summary = interview.report.summary or None
        interview_id = interview.id

    result = build_roadmap(
        resume.ats_result,
        interview_summary,
        weeks=payload.weeks,
        hours_per_week=payload.hours_per_week,
        role_key=payload.role_key or resume.role_key,
    )

    roadmap = Roadmap(
        user_id=user.id,
        resume_id=resume.id,
        interview_id=interview_id,
        role_key=result["role_key"],
        week_count=result["week_count"],
        hours_per_week=result["hours_per_week"],
        total_hours=result["total_hours"],
        coach_note=result["coach_note"],
        weeks=result["weeks"],
        gaps=result["gaps"],
        progress={},
    )
    db.add(roadmap)
    db.commit()
    db.refresh(roadmap)
    return roadmap


def _pick_resume(db, user_id: int, resume_id: int | None) -> Resume | None:
    query = select(Resume).where(Resume.user_id == user_id)
    if resume_id is not None:
        return db.scalar(query.where(Resume.id == resume_id))
    # Prefer an analysed resume - an unanalysed one has no ATS result to
    # build gaps from, so falling back to "most recent" would fail confusingly.
    return db.scalar(
        query.where(Resume.ats_score.isnot(None)).order_by(Resume.analyzed_at.desc())
    ) or db.scalar(query.order_by(Resume.created_at.desc()))
