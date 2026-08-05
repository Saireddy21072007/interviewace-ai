"""
The interview engine.

    POST /generate-questions     start an interview, get its questions
    POST /submit-answer          typed answer or code submission
    POST /submit-answer/audio    spoken answer (multipart: audio + transcript)
    POST /evaluate               score one answer, or finalise the interview
    GET  /interviews             history
    GET  /interviews/{id}        one interview with its questions and answers

WHY SUBMIT AND EVALUATE ARE SEPARATE ENDPOINTS
----------------------------------------------
The guide lists both, and they genuinely are two different operations:
submitting must be fast (the candidate is waiting to hear the next question),
while evaluating can take several seconds if an LLM is involved. `/submit-answer`
scores inline by default because that keeps the demo simple, but a client can
send `evaluate_now: false` to bank the answers and score them all at the end -
which is what you would do over a slow connection.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ai.evaluator import evaluate_answer, evaluate_code, summarise_interview
from ai.question_gen import generate_coding_problems, generate_questions
from ai.skills_db import role_or_default
from ai.stt import transcribe

from ..config import get_settings
from ..deps import CurrentUser, DbSession
from ..models import Answer, Interview, Question, Report, Resume, utcnow
from ..schemas import (
    AnswerOut, EvaluateRequest, GenerateQuestionsRequest, GenerateQuestionsResponse,
    InterviewOut, QuestionOut, SubmitAnswerRequest, SubmitAnswerResponse,
)

router = APIRouter(tags=["interviews"])
settings = get_settings()

AUDIO_SUFFIXES = {".webm", ".ogg", ".wav", ".mp3", ".m4a", ".mp4"}


# --------------------------------------------------------------------------- #
# Start an interview
# --------------------------------------------------------------------------- #


@router.post("/generate-questions", response_model=GenerateQuestionsResponse,
             status_code=status.HTTP_201_CREATED)
def generate_interview_questions(
    payload: GenerateQuestionsRequest,
    user: CurrentUser,
    db: DbSession,
) -> GenerateQuestionsResponse:
    resume = None
    if payload.resume_id is not None:
        resume = db.scalar(select(Resume).where(
            Resume.id == payload.resume_id, Resume.user_id == user.id))
        if resume is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resume not found.")
    else:
        resume = db.scalar(
            select(Resume).where(Resume.user_id == user.id)
            .order_by(Resume.is_primary.desc(), Resume.created_at.desc())
        )

    parsed = None
    if resume is not None:
        parsed = dict(resume.parsed or {})
        parsed["raw_text"] = resume.raw_text

    role_key = payload.role_key or (resume.role_key if resume else None) or user.target_role

    interview = Interview(
        user_id=user.id,
        resume_id=resume.id if resume else None,
        role_key=role_or_default(role_key)[0],
        company_key=payload.company_key,
        mode=payload.mode,
        difficulty=payload.difficulty,
        status="in_progress",
    )
    db.add(interview)
    db.flush()  # assign interview.id without committing yet

    generated: list[dict] = []
    if payload.mode != "coding":
        generated += generate_questions(
            parsed,
            role_key=interview.role_key,
            company_key=payload.company_key,
            count=payload.count,
            difficulty=payload.difficulty,
            # Seeded per interview so a candidate who reloads the page gets the
            # same interview back rather than a brand-new set of questions.
            seed=interview.id,
        )
    coding_count = payload.coding_problems or (payload.count if payload.mode == "coding" else 0)
    if coding_count:
        generated += generate_coding_problems(
            role_key=interview.role_key,
            count=coding_count,
            difficulty=payload.difficulty,
            seed=interview.id,
        )

    if not generated:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No questions could be generated. Please try again.",
        )

    rows: list[Question] = []
    for index, item in enumerate(generated, start=1):
        is_coding = item.get("category") == "coding"
        rows.append(Question(
            interview_id=interview.id,
            index=index,
            category=item.get("category", "technical"),
            skill=item.get("skill"),
            difficulty=item.get("difficulty", payload.difficulty),
            text=item.get("prompt") if is_coding else item["text"],
            expected_points=item.get("expected_points", []),
            time_limit_sec=item.get("time_limit_sec", 180),
            source=item.get("source", "bank"),
            problem={k: item[k] for k in ("slug", "title", "examples", "starter_code")
                     if k in item} if is_coding else {},
        ))
    db.add_all(rows)
    db.commit()
    db.refresh(interview)

    engine = "llm" if any(r.source == "llm" for r in rows) else "bank"
    return GenerateQuestionsResponse(
        interview=InterviewOut.model_validate(interview),
        questions=[QuestionOut.model_validate(r) for r in sorted(rows, key=lambda r: r.index)],
        engine=engine,
    )


# --------------------------------------------------------------------------- #
# Submit answers
# --------------------------------------------------------------------------- #


@router.post("/submit-answer", response_model=SubmitAnswerResponse)
def submit_answer(
    payload: SubmitAnswerRequest,
    user: CurrentUser,
    db: DbSession,
) -> SubmitAnswerResponse:
    """Typed answers and coding submissions."""
    question = _get_question(db, user.id, payload.question_id)
    answer = _upsert_answer(db, question)

    answer.transcript = payload.transcript.strip()
    answer.transcript_source = "typed"
    answer.duration_sec = payload.duration_sec
    answer.code = payload.code
    answer.language = payload.language

    if payload.evaluate_now:
        _score(answer, question)

    db.commit()
    db.refresh(answer)
    return _submit_response(db, question, answer, transcription={})


@router.post("/submit-answer/audio", response_model=SubmitAnswerResponse)
async def submit_answer_audio(
    user: CurrentUser,
    db: DbSession,
    question_id: int = Form(...),
    audio: UploadFile = File(...),
    browser_transcript: str = Form(default=""),
    duration_sec: float | None = Form(default=None),
    evaluate_now: bool = Form(default=True),
) -> SubmitAnswerResponse:
    """A spoken answer.

    The audio is kept even when the browser already transcribed it, so a better
    STT model can re-transcribe the same interview later without asking the
    candidate to sit through it again.
    """
    question = _get_question(db, user.id, question_id)

    suffix = Path(audio.filename or "").suffix.lower() or ".webm"
    if suffix not in AUDIO_SUFFIXES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported audio format '{suffix}'.",
        )

    data = await audio.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="Audio clip is too large.")

    stored_name = f"{user.id}_{question.interview_id}_{question.index}_{uuid.uuid4().hex[:8]}{suffix}"
    if data:
        (settings.audio_dir / stored_name).write_bytes(data)

    result = transcribe(data, stored_name, browser_transcript=browser_transcript)
    if not result["text"] and not browser_transcript.strip():
        # Still store the (empty) answer so the interview can move on. Refusing
        # to accept the answer would strand the candidate on question 3.
        result["note"] = result["note"] or "No speech was detected in the recording."

    answer = _upsert_answer(db, question)
    answer.transcript = result["text"]
    answer.transcript_source = result["provider"]
    answer.audio_path = stored_name if data else None
    answer.duration_sec = duration_sec or result.get("duration_sec")

    if evaluate_now and answer.transcript:
        _score(answer, question)

    db.commit()
    db.refresh(answer)
    return _submit_response(db, question, answer, transcription=result)


# --------------------------------------------------------------------------- #
# Evaluate / finalise
# --------------------------------------------------------------------------- #


@router.post("/evaluate", response_model=dict)
def evaluate(payload: EvaluateRequest, user: CurrentUser, db: DbSession) -> dict:
    """Score a single answer, or score every answer and close the interview."""
    if payload.answer_id is not None:
        answer = db.scalar(
            select(Answer).join(Interview).where(
                Answer.id == payload.answer_id, Interview.user_id == user.id)
        )
        if answer is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Answer not found.")
        question = db.get(Question, answer.question_id)
        _score(answer, question)
        db.commit()
        db.refresh(answer)
        return {"answer": AnswerOut.model_validate(answer).model_dump(mode="json")}

    if payload.interview_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Provide either interview_id or answer_id.")

    interview = _get_interview(db, user.id, payload.interview_id)
    questions = sorted(interview.questions, key=lambda q: q.index)
    answers_by_question = {a.question_id: a for a in interview.answers}

    # Score anything that was submitted with evaluate_now=false.
    for question in questions:
        answer = answers_by_question.get(question.id)
        if answer is not None and answer.evaluated_at is None:
            _score(answer, question)

    evaluations, ordered_questions = [], []
    for question in questions:
        answer = answers_by_question.get(question.id)
        if answer is None:
            continue
        evaluations.append({**(answer.evaluation or {}),
                            "scores": answer.scores or {},
                            "overall": answer.overall_score})
        ordered_questions.append({"category": question.category})

    role_title = role_or_default(interview.role_key)[1]["title"]
    summary = summarise_interview(evaluations, ordered_questions, role_title)

    if payload.finalise:
        interview.status = "completed"
        interview.completed_at = utcnow()
        interview.overall_score = summary["overall"]
        interview.duration_sec = sum(
            float(a.duration_sec or 0) for a in interview.answers)

        report = interview.report or Report(interview_id=interview.id, user_id=user.id)
        report.overall_score = summary["overall"]
        report.verdict = summary["verdict"]
        report.dimension_averages = summary["dimension_averages"]
        report.summary = summary
        report.strengths = summary["strengths"]
        report.improvements = summary["improvements"]
        db.add(report)

    db.commit()
    return {"interview_id": interview.id, "finalised": payload.finalise, "summary": summary}


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #


@router.get("/interviews", response_model=list[InterviewOut])
def list_interviews(user: CurrentUser, db: DbSession, limit: int = 25) -> list[Interview]:
    return list(db.scalars(
        select(Interview).where(Interview.user_id == user.id)
        .order_by(Interview.started_at.desc()).limit(max(1, min(limit, 100)))
    ))


@router.get("/interviews/{interview_id}", response_model=dict)
def get_interview(interview_id: int, user: CurrentUser, db: DbSession) -> dict:
    interview = _get_interview(db, user.id, interview_id)
    answers_by_question = {a.question_id: a for a in interview.answers}
    questions = sorted(interview.questions, key=lambda q: q.index)
    return {
        "interview": InterviewOut.model_validate(interview).model_dump(mode="json"),
        "questions": [QuestionOut.model_validate(q).model_dump(mode="json") for q in questions],
        "answers": [
            AnswerOut.model_validate(answers_by_question[q.id]).model_dump(mode="json")
            for q in questions if q.id in answers_by_question
        ],
    }


@router.delete("/interviews/{interview_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_model=None)
def delete_interview(interview_id: int, user: CurrentUser, db: DbSession) -> None:
    interview = _get_interview(db, user.id, interview_id)
    for answer in interview.answers:
        if answer.audio_path:
            (settings.audio_dir / answer.audio_path).unlink(missing_ok=True)
    db.delete(interview)
    db.commit()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _get_interview(db, user_id: int, interview_id: int) -> Interview:
    interview = db.scalar(
        select(Interview)
        .options(selectinload(Interview.questions), selectinload(Interview.answers))
        .where(Interview.id == interview_id, Interview.user_id == user_id)
    )
    if interview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Interview not found.")
    return interview


def _get_question(db, user_id: int, question_id: int) -> Question:
    question = db.scalar(
        select(Question).join(Interview).where(
            Question.id == question_id, Interview.user_id == user_id)
    )
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found.")
    return question


def _upsert_answer(db, question: Question) -> Answer:
    """One answer per question. Re-submitting overwrites - candidates redo
    questions, and a second row would silently double-count in the report."""
    answer = db.scalar(select(Answer).where(Answer.question_id == question.id))
    if answer is None:
        answer = Answer(interview_id=question.interview_id, question_id=question.id)
        db.add(answer)
    return answer


def _score(answer: Answer, question: Question) -> None:
    """Run the evaluator and copy the result onto the answer row."""
    question_dict = {
        "text": question.text,
        "category": question.category,
        "expected_points": question.expected_points or [],
        "skill": question.skill,
    }

    if question.category == "coding":
        problem = {**(question.problem or {}),
                   "prompt": question.text,
                   "expected_points": question.expected_points or []}
        result = evaluate_code(problem, answer.code or answer.transcript, answer.language)
    else:
        result = evaluate_answer(
            question_dict,
            answer.transcript,
            duration_sec=answer.duration_sec,
        )

    answer.overall_score = result.get("overall")
    answer.scores = result.get("scores", {})
    answer.evaluation = result
    answer.evaluated_at = utcnow()


def _submit_response(db, question: Question, answer: Answer, transcription: dict) -> SubmitAnswerResponse:
    next_question = db.scalar(
        select(Question).where(
            Question.interview_id == question.interview_id,
            Question.index == question.index + 1,
        )
    )
    total = db.scalar(select(func.count(Question.id)).where(
        Question.interview_id == question.interview_id)) or 0
    answered = db.scalar(select(func.count(Answer.id)).where(
        Answer.interview_id == question.interview_id)) or 0

    return SubmitAnswerResponse(
        answer=AnswerOut.model_validate(answer),
        transcription=transcription,
        next_question=QuestionOut.model_validate(next_question) if next_question else None,
        answered=answered,
        total=total,
    )
