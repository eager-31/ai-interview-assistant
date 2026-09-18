from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.redis_client import get_redis
from app.models import Feedback
from app.schemas.interview import (
    AnswerRequest,
    AnswerResponse,
    FeedbackRequest,
    FeedbackResponse,
    InterviewDetail,
    InterviewSummary,
    StartRequest,
    StartResponse,
    TurnOut,
)
from app.services import agent as interview_agent
from app.services import records
from app.services import session as sessions

router = APIRouter(prefix="/api/interview", tags=["interview"])


def _feedback_out(row: Feedback | None) -> FeedbackResponse | None:
    if row is None:
        return None
    return FeedbackResponse(score=row.score, feedback=row.feedback_text, areas_of_improvement=row.areas_of_improvement)


@router.post("/start", response_model=StartResponse)
async def start_interview(
    body: StartRequest,
    request: Request,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    session_id = uuid4()
    question = await interview_agent.ask_first_question(request.app.state.agent, session_id, body.subject)
    # Stores are written after the LLM call succeeds so a failed start leaves no orphan session.
    await records.create_interview(db, session_id, body.subject, question)
    await sessions.create_session(redis, session_id, body.subject)
    return StartResponse(session_id=session_id, question_number=1, question=question)


@router.post("/submit-answer", response_model=AnswerResponse)
async def submit_answer(
    body: AnswerRequest,
    request: Request,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    session = await sessions.get_session(redis, body.session_id)
    if session["status"] == "completed":
        raise HTTPException(status_code=409, detail={"error": "interview_completed", "message": "This interview is already finished."})

    question_number = int(session["question_number"])
    is_last = question_number >= interview_agent.TOTAL_QUESTIONS
    message = await interview_agent.reply_to_answer(request.app.state.agent, body.session_id, body.answer, is_last)

    await records.record_answer(db, body.session_id, question_number, body.answer, None if is_last else message)
    if is_last:
        await sessions.mark_completed(redis, body.session_id)
    else:
        question_number = await sessions.advance_question(redis, body.session_id)
    return AnswerResponse(question_number=question_number, message=message, interview_complete=is_last)


@router.post("/get-feedback", response_model=FeedbackResponse)
async def get_feedback(
    body: FeedbackRequest,
    request: Request,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    session = await sessions.get_session(redis, body.session_id)
    if session["status"] != "completed":
        raise HTTPException(status_code=409, detail={"error": "interview_not_finished", "message": "Finish all questions before requesting feedback."})

    interview = await records.get_interview(db, body.session_id)
    if interview.feedback is not None:
        return _feedback_out(interview.feedback)

    feedback = await interview_agent.generate_feedback(
        request.app.state.model, request.app.state.agent, body.session_id, session["subject"]
    )
    await records.save_feedback(db, body.session_id, feedback)
    return feedback


@router.get("/history", response_model=list[InterviewSummary])
async def interview_history(db: AsyncSession = Depends(get_db)):
    interviews = await records.list_interviews(db)
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
async def interview_detail(session_id: UUID, db: AsyncSession = Depends(get_db)):
    interview = await records.get_interview(db, session_id)
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
