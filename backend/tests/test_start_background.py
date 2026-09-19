import logging

import pytest
from langchain_google_genai.chat_models import GoogleRateLimitError

from app.main import app
from app.services.resume import MAX_RESUME_BYTES
from tests.pdf_helper import make_blank_pdf, make_pdf
from tests.test_resilience import FailingFeedbackModel

START = "/api/interview/start"


def pdf_upload(content: bytes, name: str = "cv.pdf"):
    return {"resume": (name, content, "application/pdf")}


async def system_prompt(session_id: str) -> str:
    state = await app.state.agent.aget_state({"configurable": {"thread_id": session_id}})
    return state.values["messages"][0].content


async def start(client, created, *, data=None, files=None):
    response = await client.post(START, data={"subject": "Python", **(data or {})}, files=files)
    if response.status_code == 200:
        created.append(response.json()["session_id"])
    return response


async def test_job_description_only_shapes_the_prompt(client, created_sessions):
    response = await start(client, created_sessions, data={"job_description": "We need skill-fastapi and skill-redis."})

    assert response.status_code == 200
    assert app.state.model.summary_calls == 1
    prompt = await system_prompt(response.json()["session_id"])
    assert "Target role: Stub Role" in prompt
    assert "skill-fastapi" in prompt and "skill-redis" in prompt


async def test_resume_only_shapes_the_prompt(client, created_sessions):
    resume = make_pdf("Built services with skill-postgres and skill-docker.")
    response = await start(client, created_sessions, files=pdf_upload(resume))

    assert response.status_code == 200
    prompt = await system_prompt(response.json()["session_id"])
    assert "skill-postgres" in prompt and "skill-docker" in prompt


async def test_resume_and_job_description_are_summarised_together(client, created_sessions):
    response = await start(
        client,
        created_sessions,
        data={"job_description": "Looking for skill-kafka."},
        files=pdf_upload(make_pdf("Experienced with skill-spark.")),
    )

    assert response.status_code == 200
    assert app.state.model.summary_calls == 1
    material = str(app.state.model.last_summary_input)
    assert "<resume>" in material and "<job_description>" in material
    prompt = await system_prompt(response.json()["session_id"])
    assert "skill-kafka" in prompt and "skill-spark" in prompt


async def test_without_either_the_generic_prompt_is_used_and_no_extra_llm_call_is_made(client, created_sessions):
    response = await start(client, created_sessions)

    assert response.status_code == 200
    assert app.state.model.summary_calls == 0
    assert "About the candidate" not in await system_prompt(response.json()["session_id"])


async def test_blank_job_description_and_empty_file_field_count_as_not_provided(client, created_sessions):
    response = await start(client, created_sessions, data={"job_description": "   \n"}, files={"resume": ("", b"")})

    assert response.status_code == 200
    assert app.state.model.summary_calls == 0


@pytest.mark.parametrize(
    "content,status,code",
    [
        (b"this is plain text, not a pdf", 422, "resume_unreadable"),
        (make_blank_pdf(), 422, "resume_unreadable"),
        (b"%PDF-" + b"0" * MAX_RESUME_BYTES, 413, "resume_too_large"),
    ],
    ids=["not a pdf", "no text", "too large"],
)
async def test_bad_resumes_are_rejected_before_any_llm_call(client, content, status, code):
    response = await client.post(START, data={"subject": "Python"}, files=pdf_upload(content))

    assert response.status_code == status
    assert response.json()["detail"]["error"] == code
    assert app.state.model.summary_calls == 0
    assert (await client.get("/api/interview/history")).json() == []


async def test_summary_failure_is_reported_not_silently_ignored(client):
    app.state.model = FailingFeedbackModel(GoogleRateLimitError("quota"))

    response = await client.post(START, data={"subject": "Python", "job_description": "Backend role"})

    assert response.status_code == 429
    assert response.json()["detail"]["error"] == "llm_rate_limited"
    assert (await client.get("/api/interview/history")).json() == []


@pytest.mark.parametrize(
    "data",
    [{"subject": ""}, {"subject": "Python", "job_description": "x" * 10_001}, {}],
    ids=["empty subject", "job description too long", "missing subject"],
)
async def test_invalid_form_fields_return_422(client, data):
    assert (await client.post(START, data=data)).status_code == 422


async def test_resume_text_is_never_logged(client, created_sessions, caplog):
    caplog.set_level(logging.DEBUG)
    resume = make_pdf("Confidential project skill-topsecret-payroll")

    response = await start(client, created_sessions, data={"job_description": "confidential-jd-text"}, files=pdf_upload(resume))

    assert response.status_code == 200
    rendered = " ".join(record.getMessage() + str(record.__dict__) for record in caplog.records)
    assert "skill-topsecret-payroll" not in rendered and "confidential-jd-text" not in rendered
    started = next(r for r in caplog.records if r.getMessage() == "interview started")
    assert started.used_resume is True and started.used_job_description is True
