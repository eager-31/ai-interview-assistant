import asyncio
from uuid import uuid4

from app.main import app


async def run_interview(client, created, subject, answers):
    start = await client.post("/api/interview/start", json={"subject": subject})
    assert start.status_code == 200
    session_id = start.json()["session_id"]
    created.append(session_id)

    last = None
    for answer in answers:
        last = await client.post("/api/interview/submit-answer", json={"session_id": session_id, "answer": answer})
        assert last.status_code == 200
    return session_id, last.json()


async def transcript(session_id):
    state = await app.state.agent.aget_state({"configurable": {"thread_id": session_id}})
    return " ".join(str(m.content) for m in state.values["messages"])


async def test_concurrent_sessions_do_not_share_state(client, created_sessions):
    (id_a, last_a), (id_b, last_b) = await asyncio.gather(
        run_interview(client, created_sessions, "Python", ["alpha-one", "alpha-two"]),
        run_interview(client, created_sessions, "Kubernetes", ["beta-one"]),
    )

    assert id_a != id_b
    assert last_a["question_number"] == 3
    assert last_b["question_number"] == 2

    text_a, text_b = await transcript(id_a), await transcript(id_b)
    assert "Python" in text_a and "alpha-one" in text_a and "alpha-two" in text_a
    assert "Kubernetes" not in text_a and "beta" not in text_a
    assert "Kubernetes" in text_b and "beta-one" in text_b
    assert "Python" not in text_b and "alpha" not in text_b


async def test_unknown_session_returns_404(client):
    response = await client.post("/api/interview/submit-answer", json={"session_id": str(uuid4()), "answer": "hi"})
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "session_not_found"


async def test_expired_session_returns_404(client, created_sessions):
    session_id, _ = await run_interview(client, created_sessions, "Python", ["one"])
    await app.state.redis.delete(f"session:{session_id}")

    response = await client.post("/api/interview/submit-answer", json={"session_id": session_id, "answer": "two"})
    assert response.status_code == 404


async def test_feedback_only_after_interview_and_only_own_transcript(client, created_sessions):
    (id_a, last_a), (id_b, _) = await asyncio.gather(
        run_interview(client, created_sessions, "Python", [f"alpha-{i}" for i in range(5)]),
        run_interview(client, created_sessions, "Kubernetes", [f"beta-{i}" for i in range(5)]),
    )
    assert last_a["interview_complete"] is True

    feedback_a = await client.post("/api/interview/get-feedback", json={"session_id": id_a})
    assert feedback_a.status_code == 200
    assert "alpha-4" in feedback_a.json()["feedback"]
    assert "beta" not in feedback_a.json()["feedback"]

    again = await client.post("/api/interview/submit-answer", json={"session_id": id_b, "answer": "extra"})
    assert again.status_code == 409


async def test_feedback_before_finishing_returns_409(client, created_sessions):
    session_id, _ = await run_interview(client, created_sessions, "Python", ["only-one"])
    response = await client.post("/api/interview/get-feedback", json={"session_id": session_id})
    assert response.status_code == 409
