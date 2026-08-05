"""
Resume upload and analysis.

    POST /upload-resume    multipart file -> parsed, skills detected, stored
    POST /analyze-resume   resume + role (+ optional JD) -> ATS score
    GET  /resumes          list
    GET  /resumes/{id}     detail
    DELETE /resumes/{id}

Upload and analysis are separate calls on purpose. Uploading is cheap and
always succeeds the same way; analysis depends on a role, a job description and
possibly an LLM, and a candidate re-scores the same resume against several
different roles. Merging them would mean re-uploading the file to change the
target job.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from ai.ats import narrative_review, score_resume
from ai.resume_parser import SUPPORTED_EXTENSIONS, parse_resume

from ..config import get_settings
from ..deps import CurrentUser, DbSession
from ..models import Resume, utcnow
from ..schemas import (
    AnalyzeResumeRequest, AnalyzeResumeResponse, ResumeDetail, ResumeSummary,
    UploadResumeResponse,
)

router = APIRouter(tags=["resumes"])
settings = get_settings()


@router.post("/upload-resume", response_model=UploadResumeResponse,
             status_code=status.HTTP_201_CREATED)
async def upload_resume(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(..., description="PDF, DOCX or TXT, max 10MB"),
    make_primary: bool = Form(default=True),
) -> UploadResumeResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"'{suffix or 'This file type'}' is not supported. Upload a PDF, DOCX or TXT file.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="The uploaded file was empty.")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is {len(data) / 1_048_576:.1f}MB. The limit is {settings.max_upload_mb}MB.",
        )

    parsed = parse_resume(data, file.filename)

    # Store under a generated name. User-supplied filenames are the classic
    # path-traversal vector ("../../.env"), and two candidates both uploading
    # "resume.pdf" must not collide.
    stored_name = f"{user.id}_{uuid.uuid4().hex}{suffix}"
    (settings.resume_dir / stored_name).write_bytes(data)

    if make_primary:
        for other in db.scalars(select(Resume).where(Resume.user_id == user.id, Resume.is_primary)):
            other.is_primary = False

    resume = Resume(
        user_id=user.id,
        filename=_safe_filename(file.filename),
        stored_name=stored_name,
        content_type=file.content_type or "",
        size_bytes=len(data),
        raw_text=parsed.get("raw_text", ""),
        parsed=_strip_raw_text(parsed),
        skills=parsed.get("skill_list", []),
        is_primary=make_primary,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    detected = parsed.get("skill_list", [])
    return UploadResumeResponse(
        resume=ResumeDetail.model_validate(resume),
        warnings=parsed.get("warnings", []),
        detected_skills=detected,
        message=(
            f"Read {parsed.get('signals', {}).get('word_count', 0)} words and detected "
            f"{len(detected)} skills."
            if parsed.get("ok") else
            "The file was stored but almost no text could be read from it."
        ),
    )


@router.post("/analyze-resume", response_model=AnalyzeResumeResponse)
def analyze_resume(
    payload: AnalyzeResumeRequest,
    user: CurrentUser,
    db: DbSession,
) -> AnalyzeResumeResponse:
    resume = _get_resume(db, user.id, payload.resume_id)
    parsed = dict(resume.parsed or {})
    parsed["raw_text"] = resume.raw_text  # re-attach; it is not stored inside the JSON blob

    role_key = payload.role_key or resume.role_key or user.target_role
    level = payload.experience_level or user.experience_level

    result = score_resume(
        parsed,
        role_key=role_key,
        job_description=payload.job_description,
        experience_level=level,
    )
    review = narrative_review(parsed, result)

    resume.role_key = result["role_key"]
    resume.job_description = payload.job_description or ""
    resume.ats_score = result["score"]
    resume.ats_result = {**result, "review": review}
    resume.analyzed_at = utcnow()
    db.commit()

    return AnalyzeResumeResponse(
        resume_id=resume.id,
        review=review,
        warnings=(resume.parsed or {}).get("warnings", []),
        **{key: result[key] for key in (
            "score", "grade", "band", "role_key", "role_title", "breakdown",
            "matched_skills", "missing_must_have", "missing_good_to_have",
            "extra_skills", "suggestions",
        )},
    )


@router.get("/resumes", response_model=list[ResumeSummary])
def list_resumes(user: CurrentUser, db: DbSession) -> list[Resume]:
    return list(db.scalars(
        select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc())
    ))


@router.get("/resumes/{resume_id}", response_model=ResumeDetail)
def get_resume(resume_id: int, user: CurrentUser, db: DbSession) -> Resume:
    return _get_resume(db, user.id, resume_id)


@router.get("/resumes/{resume_id}/text", response_model=dict)
def get_resume_text(resume_id: int, user: CurrentUser, db: DbSession) -> dict:
    """The extracted text, so the UI can show what the parser actually saw.

    This is the fastest way for a candidate to understand a low parseability
    score: if the preview is empty or scrambled, so is the ATS's view.
    """
    resume = _get_resume(db, user.id, resume_id)
    return {"resume_id": resume.id, "filename": resume.filename, "text": resume.raw_text}


@router.delete("/resumes/{resume_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_model=None)
def delete_resume(resume_id: int, user: CurrentUser, db: DbSession) -> None:
    resume = _get_resume(db, user.id, resume_id)
    (settings.resume_dir / resume.stored_name).unlink(missing_ok=True)
    db.delete(resume)
    db.commit()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _get_resume(db, user_id: int, resume_id: int | None) -> Resume:
    """Fetch a resume the user owns, defaulting to their primary/most recent.

    Every lookup is scoped by user_id. Filtering on the id alone would let any
    signed-in user read any other candidate's resume by guessing a number.
    """
    query = select(Resume).where(Resume.user_id == user_id)
    if resume_id is not None:
        resume = db.scalar(query.where(Resume.id == resume_id))
        if resume is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resume not found.")
        return resume

    resume = db.scalar(query.order_by(Resume.is_primary.desc(), Resume.created_at.desc()))
    if resume is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No resume uploaded yet. Upload one first.",
        )
    return resume


def _strip_raw_text(parsed: dict) -> dict:
    """raw_text has its own TEXT column; keeping a second copy in the JSON blob
    would double the row size for no benefit."""
    return {key: value for key, value in parsed.items() if key != "raw_text"}


def _safe_filename(name: str | None) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(name or "resume").name)
    return cleaned[:120] or "resume"
