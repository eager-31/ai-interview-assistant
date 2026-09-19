from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Feedback, InterviewSession, Turn
from app.schemas.interview import FeedbackResponse

# Redis holds the live interview (agent state, question counter) and expires
# after 2 hours; it is fast but temporary. These functions write the same
# interview to Postgres as it happens, which is the permanent record that
# history and transcripts are read from.


async def create_interview(
    db: AsyncSession, session_id: UUID, user_id: UUID, subject: str, first_question: str
) -> None:
    interview = InterviewSession(
        id=session_id, user_id=user_id, subject=subject, turns=[Turn(question_number=1, question_text=first_question)]
    )
    db.add(interview)
    await db.commit()


async def record_answer(
    db: AsyncSession, session_id: UUID, question_number: int, answer: str, next_question: str | None
) -> None:
    turn = (
        await db.execute(select(Turn).where(Turn.session_id == session_id, Turn.question_number == question_number))
    ).scalar_one()
    turn.answer_text = answer

    if next_question is not None:
        db.add(Turn(session_id=session_id, question_number=question_number + 1, question_text=next_question))
    else:
        interview = await db.get(InterviewSession, session_id)
        interview.status = "completed"
        interview.completed_at = datetime.now(timezone.utc)
    await db.commit()


async def get_interview(db: AsyncSession, session_id: UUID, user_id: UUID) -> InterviewSession | None:
    interview = await db.get(InterviewSession, session_id)
    if interview is None or interview.user_id != user_id:
        return None
    return interview


async def list_interviews(db: AsyncSession, user_id: UUID) -> list[InterviewSession]:
    result = await db.execute(
        select(InterviewSession).where(InterviewSession.user_id == user_id).order_by(InterviewSession.started_at.desc())
    )
    return list(result.scalars())


async def save_feedback(db: AsyncSession, session_id: UUID, feedback: FeedbackResponse) -> None:
    db.add(
        Feedback(
            session_id=session_id,
            score=feedback.score,
            feedback_text=feedback.feedback,
            areas_of_improvement=feedback.areas_of_improvement,
        )
    )
    await db.commit()
