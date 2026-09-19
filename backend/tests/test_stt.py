import json
import logging

import httpx
import pytest

from app.core.config import settings
from app.core.errors import ApiError
from app.services import stt
from tests.conftest import FakeSpeechServices, mock_http

AUDIO = b"fake-webm-bytes"


async def transcribe(fake: FakeSpeechServices) -> str:
    async with mock_http(fake) as http:
        return await stt.transcribe(http, AUDIO)


async def transcribe_error(fake: FakeSpeechServices) -> ApiError:
    with pytest.raises(ApiError) as caught:
        await transcribe(fake)
    return caught.value


async def test_uploads_audio_starts_a_transcript_and_polls_until_done():
    fake = FakeSpeechServices()
    fake.transcript = "  Lists are mutable.  "
    fake.polls_before_done = 2

    assert await transcribe(fake) == "Lists are mutable."

    upload, start = fake.calls("upload")[0], fake.calls("transcript")[0]
    assert upload.content == AUDIO
    assert upload.headers["authorization"] == "test-assemblyai-key"
    assert json.loads(start.content) == {"audio_url": "https://cdn.assemblyai.com/upload/fake", "language_detection": True}
    assert len(fake.calls("poll")) == 3


async def test_silence_comes_back_as_an_empty_string():
    fake = FakeSpeechServices()
    fake.transcript = ""
    assert await transcribe(fake) == ""


@pytest.mark.parametrize("step", ["upload", "transcript", "poll"])
async def test_a_temporary_failure_is_retried_and_the_call_succeeds(step):
    fake = FakeSpeechServices()
    fake.fail(step, 503, httpx.ConnectTimeout("slow"))

    assert await transcribe(fake) == fake.transcript
    assert len(fake.calls(step)) >= 3


async def test_gives_up_after_three_attempts():
    fake = FakeSpeechServices()
    fake.fail("transcript", 500, 500, 500, 500)

    error = await transcribe_error(fake)

    assert (error.status_code, error.error) == (502, "stt_error")
    assert len(fake.calls("transcript")) == 3


@pytest.mark.parametrize(
    "status,http_status,code",
    [(401, 502, "stt_auth_failed"), (403, 502, "stt_auth_failed"), (402, 502, "stt_quota_exceeded"), (400, 502, "stt_error")],
)
async def test_errors_that_retrying_cannot_fix_are_not_retried(status, http_status, code):
    fake = FakeSpeechServices()
    fake.fail("transcript", status)

    error = await transcribe_error(fake)

    assert (error.status_code, error.error) == (http_status, code)
    assert len(fake.calls("transcript")) == 1


async def test_rate_limiting_is_retried_and_then_reported():
    fake = FakeSpeechServices()
    fake.fail("upload", 429, 429, 429)

    error = await transcribe_error(fake)

    assert (error.status_code, error.error) == (429, "stt_rate_limited")
    assert len(fake.calls("upload")) == 3


async def test_a_timeout_is_reported_as_a_gateway_timeout():
    fake = FakeSpeechServices()
    fake.fail("upload", *[httpx.ConnectTimeout("slow")] * 3)

    error = await transcribe_error(fake)

    assert (error.status_code, error.error) == (504, "stt_timeout")


async def test_an_unreadable_recording_is_a_client_error_and_not_retried():
    fake = FakeSpeechServices()
    fake.transcript_error = "File does not appear to contain audio"

    error = await transcribe_error(fake)

    assert (error.status_code, error.error) == (422, "audio_unreadable")
    assert len(fake.calls("transcript")) == 1


async def test_a_transcript_that_never_finishes_times_out(monkeypatch):
    fake = FakeSpeechServices()
    fake.polls_before_done = 10**9
    monkeypatch.setattr(stt, "MAX_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(stt, "POLL_INTERVAL_SECONDS", 0.01)

    error = await transcribe_error(fake)

    assert (error.status_code, error.error) == (504, "stt_timeout")


async def test_without_an_api_key_it_fails_before_any_network_call(monkeypatch):
    fake = FakeSpeechServices()
    monkeypatch.setattr(settings, "assemblyai_api_key", "")

    error = await transcribe_error(fake)

    assert (error.status_code, error.error) == (503, "stt_not_configured")
    assert fake.requests == []


async def test_the_api_key_is_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    fake = FakeSpeechServices()
    fake.fail("upload", 503)
    fake.fail("transcript", 401)

    await transcribe_error(fake)

    assert "test-assemblyai-key" not in " ".join(str(r.__dict__) + r.getMessage() for r in caplog.records)
