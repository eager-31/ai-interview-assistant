from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StartRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=100)


class StartResponse(BaseModel):
    session_id: UUID
    question_number: int
    question: str


class AnswerRequest(BaseModel):
    session_id: UUID
    answer: str = Field(min_length=1, max_length=5000)


class AnswerResponse(BaseModel):
    question_number: int
    message: str
    interview_complete: bool


class FeedbackRequest(BaseModel):
    session_id: UUID


class FeedbackResponse(BaseModel):
    score: int = Field(ge=1, le=5, description="Overall candidate score from 1 (weak) to 5 (excellent)")
    feedback: str = Field(description="Strengths, citing things the candidate actually said")
    areas_of_improvement: str = Field(description="Concrete suggestions based on gaps in their answers")


class TurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_number: int
    question_text: str
    answer_text: str | None


class InterviewSummary(BaseModel):
    id: UUID
    subject: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    score: int | None


class InterviewDetail(BaseModel):
    id: UUID
    subject: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    turns: list[TurnOut]
    feedback: FeedbackResponse | None
