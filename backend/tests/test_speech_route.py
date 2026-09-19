import json
import logging
from uuid import uuid4


from app.core.config import settings
from app.main import app
from tests.conftest import FakeSpeechServices
from tests.test_sessions import run_interview

START = "/api/interview/start"
FRONTEND = "http://localhost:5173"


def speech_url(session_id: str) -> str:
    return f"/api/interview/{session_id}/speech"


async def start_interview(client, created) -> str:
    response = await client.post(START, data={"subject": "Python"})
    created.append(response.json()["session_id"])
    return response.json()["session_id"]


def spoken_text() -> str:
    return json.loads(app.state.speech.calls("murf")[-1].content)["text"]


async def test_streams_the_interviewers_opening_question(client, created_sessions):
    session_id = await start_interview(client, created_sessions)
    question = (await client.get(f"/api/interview/{session_id}")).json()["turns"][0]["question_text"]

    response = await client.get(speech_url(session_id))

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == FakeSpeechServices.AUDIO
    assert response.headers["x-question-number"] == "1"
    assert response.headers["x-interview-complete"] == "false"
    assert response.headers["cache-control"] == "no-store"
    assert spoken_text() == question


async def test_after_an_answer_it_speaks_the_new_message_and_the_number_moves_on(client, created_sessions):
    session_id, last = await run_interview(client, created_sessions, "Python", ["my first answer"])

    response = await client.get(speech_url(session_id))

    assert response.headers["x-question-number"] == "2"
    assert spoken_text() == last["message"]


async def test_after_the_last_answer_it_speaks_the_closing_message_and_says_the_interview_is_complete(client, created_sessions):
    session_id, last = await run_interview(client, created_sessions, "Python", [f"answer {i}" for i in range(5)])

    response = await client.get(speech_url(session_id))

    assert response.headers["x-question-number"] == "5"
    assert response.headers["x-interview-complete"] == "true"
    assert spoken_text() == last["message"]


async def test_it_cannot_be_used_to_say_arbitrary_text(client, created_sessions):
    session_id = await start_interview(client, created_sessions)

    await client.get(speech_url(session_id), params={"text": "read this out instead"})

    assert "read this out instead" not in spoken_text()


async def test_it_needs_a_token(anonymous_client):
    assert (await anonymous_client.get(speech_url(str(uuid4())))).status_code == 401


async def test_other_peoples_sessions_are_not_found_and_cost_nothing(client, other_client, created_sessions):
    session_id = await start_interview(client, created_sessions)

    assert (await other_client.get(speech_url(session_id))).status_code == 404
    assert (await client.get(speech_url(str(uuid4())))).status_code == 404
    assert app.state.speech.calls("murf") == []


async def test_a_murf_failure_is_a_json_error_not_broken_audio(client, created_sessions):
    session_id = await start_interview(client, created_sessions)
    app.state.speech.fail("murf", 403)

    response = await client.get(speech_url(session_id))

    assert response.status_code == 502
    assert response.headers["content-type"] == "application/json"
    assert response.json()["detail"]["error"] == "tts_auth_failed"


async def test_a_temporary_murf_failure_is_retried_and_the_listener_never_notices(client, created_sessions):
    session_id = await start_interview(client, created_sessions)
    app.state.speech.fail("murf", 503)

    response = await client.get(speech_url(session_id))

    assert response.status_code == 200 and response.content == FakeSpeechServices.AUDIO
    assert len(app.state.speech.calls("murf")) == 2


async def test_without_a_murf_key_it_says_so(client, created_sessions, monkeypatch):
    session_id = await start_interview(client, created_sessions)
    monkeypatch.setattr(settings, "murf_api_key", "")

    response = await client.get(speech_url(session_id))

    assert (response.status_code, response.json()["detail"]["error"]) == (503, "tts_not_configured")


async def test_a_session_from_before_this_feature_has_nothing_to_speak(client, created_sessions):
    session_id = await start_interview(client, created_sessions)
    await app.state.redis.hdel(f"session:{session_id}", "last_message")

    response = await client.get(speech_url(session_id))

    assert (response.status_code, response.json()["detail"]["error"]) == (409, "nothing_to_speak")


async def test_the_speech_route_is_rate_limited(client, created_sessions, monkeypatch):
    session_id = await start_interview(client, created_sessions)
    monkeypatch.setattr(settings, "submit_answer_rate_limit", "2/minute")

    statuses = [(await client.get(speech_url(session_id))).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


async def test_the_api_key_never_reaches_the_client_or_the_logs(client, created_sessions, caplog):
    caplog.set_level(logging.DEBUG)
    session_id = await start_interview(client, created_sessions)
    app.state.speech.fail("murf", 503)

    response = await client.get(speech_url(session_id))

    everything = str(response.headers) + response.text + " ".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "test-murf-key" not in everything


# ---- what the browser needs from CORS ----

async def test_the_frontend_origin_may_call_the_api_and_send_its_token(client):
    preflight = await client.options(
        "/api/interview/start",
        headers={"Origin": FRONTEND, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"},
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == FRONTEND
    assert "authorization" in preflight.headers["access-control-allow-headers"].lower()


async def test_other_origins_are_refused(client):
    preflight = await client.options(
        "/api/interview/start",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )

    assert "access-control-allow-origin" not in preflight.headers


async def test_the_progress_headers_are_readable_from_javascript(client, created_sessions):
    session_id = await start_interview(client, created_sessions)

    response = await client.get(speech_url(session_id), headers={"Origin": FRONTEND})

    exposed = response.headers["access-control-expose-headers"].lower()
    assert "x-question-number" in exposed and "x-interview-complete" in exposed
    assert response.headers["access-control-allow-origin"] == FRONTEND
