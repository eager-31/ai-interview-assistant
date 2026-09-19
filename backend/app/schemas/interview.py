from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_ANSWER_CHARS = 5000


class BackgroundSummary(BaseModel):
    """What the interviewer needs to know about the candidate, extracted from a resume and/or job description."""

    target_role: str = Field(default="", description="The role the candidate is interviewing for, if stated")
    key_skills: list[str] = Field(default_factory=list, description="Up to 12 of the most relevant skills or technologies")
    experience_summary: str = Field(default="", description="Two or three sentences on the candidate's relevant experience")
    notable_projects: list[str] = Field(default_factory=list, description="Up to 5 projects or achievements worth asking about")


class StartResponse(BaseModel):
    session_id: UUID
    question_number: int
    question: str


class AnswerRequest(BaseModel):
    session_id: UUID
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)


class AnswerResponse(BaseModel):
    question_number: int
    message: str
    interview_complete: bool


class AudioAnswerResponse(AnswerResponse):
    transcript: str


class FeedbackRequest(BaseModel):
    session_id: UUID


class AnswerScore(BaseModel):
    """The model's grade for a single answer."""

    correctness: int = Field(ge=1, le=5, description="1 = mostly wrong, 5 = fully accurate")
    clarity: int = Field(ge=1, le=5, description="1 = confusing, 5 = well organised and easy to follow")
    depth: int = Field(ge=1, le=5, description="1 = surface level, 5 = covers trade-offs, examples and edge cases")
    comment: str = Field(description="One sentence explaining the scores")


class FeedbackEvaluation(BaseModel):
    """What the model writes for the final feedback. The numeric scores are added afterwards, in code."""

    overall_score: int = Field(ge=1, le=5, description="Overall candidate score from 1 (weak) to 5 (excellent)")
    feedback: str = Field(description="Strengths, citing things the candidate actually said")
    areas_of_improvement: str = Field(description="Concrete suggestions based on gaps in their answers")


class FeedbackResponse(BaseModel):
    score: int = Field(ge=1, le=5)
    correctness: float | None
    clarity: float | None
    depth: float | None
    feedback: str
    areas_of_improvement: str


class TurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_number: int
    question_text: str
    answer_text: str | None
    correctness: int | None
    clarity: int | None
    depth: int | None
    score_comment: str | None


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
