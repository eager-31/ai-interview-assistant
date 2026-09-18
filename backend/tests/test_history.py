from uuid import uuid4

from app.main import app
from tests.conftest import running_app
from tests.test_sessions import run_interview


async def test_finished_interview_is_stored_with_transcript(client, created_sessions):
    answers = [f"my-answer-{i}" for i in range(1, 6)]
    session_id, _ = await run_interview(client, created_sessions, "Python", answers)

    detail = (await client.get(f"/api/interview/{session_id}")).json()
    assert detail["status"] == "completed"
    assert detail["completed_at"] is not None
    assert [t["question_number"] for t in detail["turns"]] == [1, 2, 3, 4, 5]
    assert [t["answer_text"] for t in detail["turns"]] == answers
    assert all(t["question_text"] for t in detail["turns"])
    assert detail["feedback"] is None


async def test_unfinished_interview_has_unanswered_last_turn(client, created_sessions):
    session_id, _ = await run_interview(client, created_sessions, "Python", ["a-one", "a-two"])

    detail = (await client.get(f"/api/interview/{session_id}")).json()
    assert detail["status"] == "in_progress"
    assert [t["answer_text"] for t in detail["turns"]] == ["a-one", "a-two", None]


async def test_feedback_is_saved_and_reused(client, created_sessions):
    session_id, _ = await run_interview(client, created_sessions, "Python", [f"ans-{i}" for i in range(5)])

    first = await client.post("/api/interview/get-feedback", json={"session_id": session_id})
    second = await client.post("/api/interview/get-feedback", json={"session_id": session_id})
    assert first.json() == second.json()
    assert app.state.model.calls == 1

    detail = (await client.get(f"/api/interview/{session_id}")).json()
    assert detail["feedback"] == first.json()


async def test_history_lists_interviews_with_score(client, created_sessions):
    done_id, _ = await run_interview(client, created_sessions, "Python", [f"ans-{i}" for i in range(5)])
    await client.post("/api/interview/get-feedback", json={"session_id": done_id})
    open_id, _ = await run_interview(client, created_sessions, "Go", ["only-one"])

    history = {item["id"]: item for item in (await client.get("/api/interview/history")).json()}
    assert history[done_id]["status"] == "completed" and history[done_id]["score"] == 3
    assert history[open_id]["status"] == "in_progress" and history[open_id]["score"] is None


async def test_unknown_interview_returns_404(client):
    response = await client.get(f"/api/interview/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "interview_not_found"


async def test_interview_survives_app_restart(created_sessions):
    async with running_app() as first_run:
        session_id, _ = await run_interview(first_run, created_sessions, "Python", [f"ans-{i}" for i in range(5)])
        await first_run.post("/api/interview/get-feedback", json={"session_id": session_id})

    async with running_app() as second_run:
        detail = (await second_run.get(f"/api/interview/{session_id}")).json()
        assert len(detail["turns"]) == 5
        assert detail["feedback"]["score"] == 3
