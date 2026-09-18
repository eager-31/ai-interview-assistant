from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis

from app.core.redis_client import get_redis
from app.schemas.interview import (
    AnswerRequest,
    AnswerResponse,
    FeedbackRequest,
    FeedbackResponse,
    StartRequest,
    StartResponse,
)
from app.services import agent as interview_agent
from app.services import session as sessions

router = APIRouter(prefix="/api/interview", tags=["interview"])


@router.post("/start", response_model=StartResponse)
async def start_interview(body: StartRequest, request: Request, redis: Redis = Depends(get_redis)):
    session_id = uuid4()
    question = await interview_agent.ask_first_question(request.app.state.agent, session_id, body.subject)
    # Metadata is written after the LLM call succeeds so a failed start leaves no orphan session.
    await sessions.create_session(redis, session_id, body.subject)
    return StartResponse(session_id=session_id, question_number=1, question=question)


@router.post("/submit-answer", response_model=AnswerResponse)
async def submit_answer(body: AnswerRequest, request: Request, redis: Redis = Depends(get_redis)):
    session = await sessions.get_session(redis, body.session_id)
    if session["status"] == "completed":
        raise HTTPException(status_code=409, detail={"error": "interview_completed", "message": "This interview is already finished."})

    question_number = int(session["question_number"])
    is_last = question_number >= interview_agent.TOTAL_QUESTIONS
    message = await interview_agent.reply_to_answer(request.app.state.agent, body.session_id, body.answer, is_last)

    if is_last:
        await sessions.mark_completed(redis, body.session_id)
    else:
        question_number = await sessions.advance_question(redis, body.session_id)
    return AnswerResponse(question_number=question_number, message=message, interview_complete=is_last)


@router.post("/get-feedback", response_model=FeedbackResponse)
async def get_feedback(body: FeedbackRequest, request: Request, redis: Redis = Depends(get_redis)):
    session = await sessions.get_session(redis, body.session_id)
    if session["status"] != "completed":
        raise HTTPException(status_code=409, detail={"error": "interview_not_finished", "message": "Finish all questions before requesting feedback."})
    return await interview_agent.generate_feedback(
        request.app.state.model, request.app.state.agent, body.session_id, session["subject"]
    )
