import logging

import httpx
import pytest

from app.core.config import settings
from app.main import app
from app.services import stt
from tests.test_sessions import run_interview

START = "/api/interview/start"
AUDIO_ANSWER = "/api/interview/submit-answer-audio"


class CountingAgent:
    """Wraps the working agent and counts how often the interviewer LLM is asked for a reply."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def ainvoke(self, *args, **kwargs):
        self.calls += 1
        return await self.inner.ainvoke(*args, **kwargs)


def spoken(session_id: str, content: bytes = b"fake-webm-audio"):
    return {"data": {"session_id": session_id}, "files": {"audio": ("answer.webm", content, "audio/webm")}}


async def start_interview(client, created) -> str:
    response = await client.post(START, data={"subject": "Python"})
    created.append(response.json()["session_id"])
    return response.json()["session_id"]


async def turns(client, session_id):
    return (await client.get(f"/api/interview/{session_id}")).json()["turns"]


async def test_a_spoken_answer_goes_through_the_same_pipeline_as_a_typed_one(client, created_sessions):
    session_id = await start_interview(client, created_sessions)
    app.state.speech.transcript = "a strong spoken answer"

    response = await client.post(AUDIO_ANSWER, **spoken(session_id))

    body = response.json()
    assert response.status_code == 200
    assert body["transcript"] == "a strong spoken answer"
    assert body["question_number"] == 2 and body["interview_complete"] is False and body["message"]

    first = (await turns(client, session_id))[0]
    assert first["answer_text"] == "a strong spoken answer"
    assert (first["correctness"], first["clarity"], first["depth"]) == (5, 5, 5)
    assert "a strong spoken answer" in app.state.model.score_inputs[0]
    assert app.state.speech.calls("upload")[0].content == b"fake-webm-audio"


async def test_a_whole_interview_can_be_answered_by_voice(client, created_sessions):
    session_id = await start_interview(client, created_sessions)
    app.state.speech.transcript = "a strong spoken answer"

    for expected in (2, 3, 4, 5, 5):
        body = (await client.post(AUDIO_ANSWER, **spoken(session_id))).json()
        assert body["question_number"] == expected
    assert body["interview_complete"] is True

    feedback = await client.post("/api/interview/get-feedback", json={"session_id": session_id})
    assert feedback.status_code == 200 and feedback.json()["score"] == 5


async def test_the_session_remembers_what_the_interviewer_last_said(client, created_sessions):
    session_id = await start_interview(client, created_sessions)
    stored = lambda: app.state.redis.hget(f"session:{session_id}", "last_message")

    first_question = (await client.get(f"/api/interview/{session_id}")).json()["turns"][0]["question_text"]
    assert await stored() == first_question

    reply = (await client.post(AUDIO_ANSWER, **spoken(session_id))).json()["message"]
    assert await stored() == reply

    for _ in range(3):
        await client.post(AUDIO_ANSWER, **spoken(session_id))
    closing = (await client.post(AUDIO_ANSWER, **spoken(session_id))).json()
    assert closing["interview_complete"] and await stored() == closing["message"]


async def test_the_audio_route_needs_a_token(anonymous_client):
    response = await anonymous_client.post(AUDIO_ANSWER, **spoken("00000000-0000-0000-0000-000000000000"))
    assert response.status_code == 401


async def test_someone_elses_session_is_not_found_and_costs_nothing(client, other_client, created_sessions):
    session_id = await start_interview(client, created_sessions)

    response = await other_client.post(AUDIO_ANSWER, **spoken(session_id))

    assert response.status_code == 404
    assert app.state.speech.requests == []


async def test_a_finished_interview_is_refused_before_any_transcription(client, created_sessions):
    session_id, _ = await run_interview(client, created_sessions, "Python", [f"answer {i}" for i in range(5)])

    response = await client.post(AUDIO_ANSWER, **spoken(session_id))

    assert response.status_code == 409
    assert app.state.speech.requests == []


async def test_silence_is_rejected_and_the_interview_is_left_alone(client, created_sessions):
    session_id = await start_interview(client, created_sessions)
    agent = app.state.agent = CountingAgent(app.state.agent)
    app.state.speech.transcript = ""

    response = await client.post(AUDIO_ANSWER, **spoken(session_id))

    assert response.status_code == 422 and response.json()["detail"]["error"] == "no_speech_detected"
    assert agent.calls == 0
    assert (await turns(client, session_id))[0]["answer_text"] is None


async def test_empty_and_oversized_recordings_are_rejected_without_transcribing(client, created_sessions, monkeypatch):
    session_id = await start_interview(client, created_sessions)
    monkeypatch.setattr(stt, "MAX_AUDIO_BYTES", 100)

    empty = await client.post(AUDIO_ANSWER, **spoken(session_id, b""))
    huge = await client.post(AUDIO_ANSWER, **spoken(session_id, b"x" * 101))

    assert (empty.status_code, empty.json()["detail"]["error"]) == (422, "audio_empty")
    assert (huge.status_code, huge.json()["detail"]["error"]) == (413, "audio_too_large")
    assert app.state.speech.requests == []


async def test_a_recording_that_cannot_be_read_is_a_client_error(client, created_sessions):
    session_id = await start_interview(client, created_sessions)
    app.state.speech.transcript_error = "File does not appear to contain audio"

    response = await client.post(AUDIO_ANSWER, **spoken(session_id))

    assert (response.status_code, response.json()["detail"]["error"]) == (422, "audio_unreadable")


@pytest.mark.parametrize(
    "step,outcomes,status,code",
    [
        ("upload", [401], 502, "stt_auth_failed"),
        ("transcript", [402], 502, "stt_quota_exceeded"),
        ("upload", [429, 429, 429], 429, "stt_rate_limited"),
        ("poll", [httpx.ReadTimeout("slow")] * 3, 504, "stt_timeout"),
        ("upload", [503, 503, 503], 502, "stt_error"),
    ],
    ids=["auth", "credit", "rate limit", "timeout", "outage"],
)
async def test_transcription_failures_are_mapped_and_leave_the_interview_untouched(
    client, created_sessions, step, outcomes, status, code
):
    session_id = await start_interview(client, created_sessions)
    agent = app.state.agent = CountingAgent(app.state.agent)
    app.state.speech.fail(step, *outcomes)

    response = await client.post(AUDIO_ANSWER, **spoken(session_id))

    assert (response.status_code, response.json()["detail"]["error"]) == (status, code)
    assert agent.calls == 0
    assert (await turns(client, session_id))[0]["answer_text"] is None

    retry = await client.post(AUDIO_ANSWER, **spoken(session_id))  # the same question can still be answered
    assert retry.status_code == 200 and retry.json()["question_number"] == 2


async def test_without_an_assemblyai_key_the_model_is_never_called(client, created_sessions, monkeypatch):
    session_id = await start_interview(client, created_sessions)
    agent = app.state.agent = CountingAgent(app.state.agent)
    monkeypatch.setattr(settings, "assemblyai_api_key", "")

    response = await client.post(AUDIO_ANSWER, **spoken(session_id))

    assert (response.status_code, response.json()["detail"]["error"]) == (503, "stt_not_configured")
    assert agent.calls == 0


async def test_a_missing_session_id_is_a_validation_error(client):
    response = await client.post(AUDIO_ANSWER, files={"audio": ("answer.webm", b"x", "audio/webm")})
    assert response.status_code == 422


async def test_an_overlong_transcript_is_cut_to_the_answer_limit(client, created_sessions):
    session_id = await start_interview(client, created_sessions)
    app.state.speech.transcript = "x" * 6000

    response = await client.post(AUDIO_ANSWER, **spoken(session_id))

    assert len(response.json()["transcript"]) == 5000
    assert len((await turns(client, session_id))[0]["answer_text"]) == 5000


async def test_the_audio_route_is_rate_limited(client, created_sessions, monkeypatch):
    session_id = await start_interview(client, created_sessions)
    monkeypatch.setattr(settings, "submit_answer_rate_limit", "2/minute")

    statuses = [(await client.post(AUDIO_ANSWER, **spoken(session_id))).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


async def test_what_was_said_is_never_written_to_the_logs(client, created_sessions, caplog):
    caplog.set_level(logging.DEBUG)
    session_id = await start_interview(client, created_sessions)
    app.state.speech.transcript = "my confidential spoken salary expectations"

    await client.post(AUDIO_ANSWER, **spoken(session_id))

    rendered = " ".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "confidential spoken salary" not in rendered
    assert any(r.getMessage() == "answer transcribed" for r in caplog.records)
