import asyncio
import logging
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.limiter import limiter
from app.core.logging import bind_session
from app.core.redis_client import get_redis
from app.core.security import get_current_user
from app.models import Feedback, User
from app.schemas.interview import (
    AnswerRequest,
    AnswerScore,
    AnswerResponse,
    FeedbackRequest,
    FeedbackResponse,
    InterviewDetail,
    InterviewSummary,
    StartResponse,
    TurnOut,
)
from app.services import agent as interview_agent
from app.services import records, scoring
from app.services.resume import MAX_RESUME_BYTES, ResumeError, extract_resume_text
from app.services import session as sessions

router = APIRouter(prefix="/api/interview", tags=["interview"])
logger = logging.getLogger(__name__)


def _feedback_out(row: Feedback | None) -> FeedbackResponse | None:
    if row is None:
        return None
    return FeedbackResponse(
        score=row.score,
        correctness=row.correctness_avg,
        clarity=row.clarity_avg,
        depth=row.depth_avg,
        feedback=row.feedback_text,
        areas_of_improvement=row.areas_of_improvement,
    )


async def _score_without_failing(model, subject: str, question: str, answer: str) -> AnswerScore | None:
    """A missing score is better than a failed interview turn, so any scoring error ends up here as None.
    The reply to the candidate is what the turn needs; scores are extra."""
    try:
        return await scoring.score_answer(model, subject, question, answer)
    except Exception:
        logger.warning("answer left unscored", exc_info=True)
        return None


async def _read_resume(upload: UploadFile | None) -> str | None:
    # Browsers send an empty file part when no file was chosen; that means "no resume".
    if upload is None or not upload.filename:
        return None
    data = await upload.read(MAX_RESUME_BYTES + 1)
    if len(data) > MAX_RESUME_BYTES:
        raise ApiError(413, "resume_too_large", f"The resume must be {MAX_RESUME_BYTES // (1024 * 1024)} MB or smaller.")
    try:
        # pypdf is synchronous and CPU-bound, so it runs off the event loop.
        return await asyncio.to_thread(extract_resume_text, data)
    except ResumeError as exc:
        raise ApiError(422, "resume_unreadable", str(exc)) from exc


@router.post("/start", response_model=StartResponse)
async def start_interview(
    request: Request,
    subject: Annotated[str, Form(min_length=1, max_length=100)],
    job_description: Annotated[str | None, Form(max_length=10_000)] = None,
    resume: UploadFile | None = None,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session_id = uuid4()
    bind_session(session_id)
    # An empty textarea arrives as "" or whitespace, which means "not provided".
    job_description = (job_description or "").strip() or None
    resume_text = await _read_resume(resume)
    background = None
    if resume_text or job_description:
        background = await interview_agent.summarize_background(request.app.state.model, resume_text, job_description)
    system_prompt = interview_agent.build_system_prompt(subject, background)
    question = await interview_agent.ask_first_question(request.app.state.agent, session_id, subject, system_prompt)
    # Stores are written after the LLM call succeeds so a failed start leaves no orphan session.
    await records.create_interview(db, session_id, user.id, subject, question)
    await sessions.create_session(redis, session_id, user.id, subject)
    logger.info(
        "interview started",
        extra={"subject": subject, "user_id": str(user.id), "used_resume": bool(resume_text), "used_job_description": bool(job_description)},
    )
    return StartResponse(session_id=session_id, question_number=1, question=question)


@router.post("/submit-answer", response_model=AnswerResponse)
@limiter.limit(lambda: settings.submit_answer_rate_limit)
async def submit_answer(
    body: AnswerRequest,
    request: Request,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bind_session(body.session_id)
    session = await sessions.get_session(redis, body.session_id, user.id)
    if session["status"] == "completed":
        raise HTTPException(status_code=409, detail={"error": "interview_completed", "message": "This interview is already finished."})

    question_number = int(session["question_number"])
    is_last = question_number >= interview_agent.TOTAL_QUESTIONS
    turn = await records.get_turn(db, body.session_id, question_number)
    # Independent calls, so they run together instead of one after the other.
    message, score = await asyncio.gather(
        interview_agent.reply_to_answer(request.app.state.agent, body.session_id, body.answer, is_last),
        _score_without_failing(request.app.state.model, session["subject"], turn.question_text, body.answer),
    )

    await records.record_answer(db, turn, body.answer, None if is_last else message, score)
    if is_last:
        await sessions.mark_completed(redis, body.session_id)
    else:
        question_number = await sessions.advance_question(redis, body.session_id)
    logger.info(
        "answer recorded",
        extra={"question_number": question_number, "interview_complete": is_last, "scored": score is not None},
    )
    return AnswerResponse(question_number=question_number, message=message, interview_complete=is_last)


@router.post("/get-feedback", response_model=FeedbackResponse)
async def get_feedback(
    body: FeedbackRequest,
    request: Request,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bind_session(body.session_id)
    session = await sessions.get_session(redis, body.session_id, user.id)
    if session["status"] != "completed":
        raise HTTPException(status_code=409, detail={"error": "interview_not_finished", "message": "Finish all questions before requesting feedback."})

    interview = await records.get_interview(db, body.session_id, user.id)
    if interview.feedback is not None:
        return _feedback_out(interview.feedback)

    evaluation = await interview_agent.generate_feedback(
        request.app.state.model,
        request.app.state.agent,
        body.session_id,
        session["subject"],
        scoring.describe_scores(interview.turns),
    )
    feedback = scoring.build_feedback(evaluation, interview.turns)
    await records.save_feedback(db, body.session_id, feedback)
    logger.info("feedback generated", extra={"score": feedback.score})
    return feedback


@router.get("/history", response_model=list[InterviewSummary])
async def interview_history(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    interviews = await records.list_interviews(db, user.id)
    return [
        InterviewSummary(
            id=i.id,
            subject=i.subject,
            status=i.status,
            started_at=i.started_at,
            completed_at=i.completed_at,
            score=i.feedback.score if i.feedback else None,
        )
        for i in interviews
    ]


@router.get("/{session_id}", response_model=InterviewDetail)
async def interview_detail(
    session_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    bind_session(session_id)
    interview = await records.get_interview(db, session_id, user.id)
    if interview is None:
        raise HTTPException(status_code=404, detail={"error": "interview_not_found", "message": "No interview with that id."})
    return InterviewDetail(
        id=interview.id,
        subject=interview.subject,
        status=interview.status,
        started_at=interview.started_at,
        completed_at=interview.completed_at,
        turns=[TurnOut.model_validate(t) for t in interview.turns],
        feedback=_feedback_out(interview.feedback),
    )
