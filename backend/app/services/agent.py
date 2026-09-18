from uuid import UUID

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.schemas.interview import FeedbackResponse

TOTAL_QUESTIONS = 5

INTERVIEW_PROMPT = """You are Natalie, a friendly and conversational interviewer conducting a natural {subject} interview.

Guidelines:
1. Ask exactly {total} questions in total, one per turn.
2. Keep questions short (1-2 sentences).
3. Refer only to what the candidate actually said in their previous answer. Never invent or assume their answers.
4. Briefly acknowledge their real answer, then adapt: go deeper if they are strong, simplify if they are unsure.
5. Be warm but concise."""

FEEDBACK_PROMPT = """The {subject} interview is over. Review the whole conversation above and evaluate the candidate.
Be specific and refer to things they actually said."""

CLOSING_NOTE = (
    "[Interviewer note: that was the final question. Briefly acknowledge the "
    "candidate's last answer and tell them the interview is complete. Keep it short.]"
)


def build_agent(model, checkpointer):
    return create_agent(model=model, tools=[], checkpointer=checkpointer)


def _config(session_id: UUID) -> dict:
    return {"configurable": {"thread_id": str(session_id)}}


async def ask_first_question(agent, session_id: UUID, subject: str) -> str:
    result = await agent.ainvoke(
        {
            "messages": [
                {"role": "system", "content": INTERVIEW_PROMPT.format(subject=subject, total=TOTAL_QUESTIONS)},
                {"role": "user", "content": f"Start the interview with a short greeting and ask the first question about {subject}."},
            ]
        },
        config=_config(session_id),
    )
    return result["messages"][-1].text


async def reply_to_answer(agent, session_id: UUID, answer: str, is_last: bool) -> str:
    messages = [HumanMessage(answer)]
    if is_last:
        messages.append(HumanMessage(CLOSING_NOTE))
    result = await agent.ainvoke({"messages": messages}, config=_config(session_id))
    return result["messages"][-1].text


async def generate_feedback(model, agent, session_id: UUID, subject: str) -> FeedbackResponse:
    state = await agent.aget_state(_config(session_id))
    transcript = state.values["messages"]
    # Called on the model directly, not through the agent, so the feedback
    # request is not written into the interview's conversation history.
    evaluator = model.with_structured_output(FeedbackResponse)
    return await evaluator.ainvoke([*transcript, HumanMessage(FEEDBACK_PROMPT.format(subject=subject))])
