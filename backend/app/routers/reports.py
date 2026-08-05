"""
GET /report - the interview report.

With no arguments it returns the most recent completed interview, because that
is what "show me my report" means 95% of the time. Pass `interview_id` for any
specific one.

This is the endpoint that exposes `expected_points`. During the interview they
are hidden (see schemas.QuestionOut); afterwards they are the most valuable
thing on the page, because "here is what a strong answer contains, and here is
what you said" is the whole feedback loop.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ai.skills_db import role_or_default

from ..deps import CurrentUser, DbSession
from ..models import Interview
from ..schemas import InterviewOut, ReportOut, ReportQuestionDetail

router = APIRouter(tags=["reports"])


@router.get("/report", response_model=ReportOut)
def get_report(user: CurrentUser, db: DbSession, interview_id: int | None = None) -> ReportOut:
    query = (
        select(Interview)
        .options(selectinload(Interview.questions), selectinload(Interview.answers),
                 selectinload(Interview.report))
        .where(Interview.user_id == user.id)
    )
    if interview_id is not None:
        interview = db.scalar(query.where(Interview.id == interview_id))
        if interview is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Interview not found.")
    else:
        interview = db.scalar(
            query.where(Interview.status == "completed").order_by(Interview.completed_at.desc())
        ) or db.scalar(query.order_by(Interview.started_at.desc()))
        if interview is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="No interviews yet. Take a mock interview to get a report.",
            )

    answers_by_question = {a.question_id: a for a in interview.answers}
    questions = sorted(interview.questions, key=lambda q: q.index)

    details: list[ReportQuestionDetail] = []
    for question in questions:
        answer = answers_by_question.get(question.id)
        details.append(ReportQuestionDetail(
            index=question.index,
            category=question.category,
            skill=question.skill,
            difficulty=question.difficulty,
            question=question.text,
            expected_points=[str(p) for p in (question.expected_points or [])],
            transcript=answer.transcript if answer else "",
            code=answer.code if answer else "",
            duration_sec=answer.duration_sec if answer else None,
            overall_score=answer.overall_score if answer else None,
            scores=answer.scores if answer else {},
            evaluation=answer.evaluation if answer else {},
        ))

    report = interview.report
    summary = (report.summary if report else {}) or {}
    role_title = role_or_default(interview.role_key)[1]["title"]

    return ReportOut(
        interview=InterviewOut.model_validate(interview),
        overall_score=report.overall_score if report else (interview.overall_score or 0),
        verdict=report.verdict if report else "Interview not finished yet",
        headline=summary.get("headline", f"Mock interview for {role_title}"),
        dimension_averages=summary.get("dimension_averages", {}),
        by_category=summary.get("by_category", {}),
        strengths=report.strengths if report else [],
        improvements=report.improvements if report else [],
        answered=summary.get("answered", len(answers_by_question)),
        total=summary.get("total", len(questions)),
        questions=details,
        created_at=report.created_at if report else None,
    )
