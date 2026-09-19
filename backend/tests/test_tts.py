import json
import logging

import httpx
import pytest

from app.core.config import settings
from app.core.errors import ApiError
from app.services import tts
from tests.conftest import FakeSpeechServices, mock_http


class Chunks(httpx.AsyncByteStream):
    def __init__(self, *pieces: bytes, then_fail: bool = False):
        self.pieces = pieces
        self.then_fail = then_fail

    async def __aiter__(self):
        for piece in self.pieces:
            yield piece
        if self.then_fail:
            raise httpx.ReadError("connection dropped")


async def speak(fake: FakeSpeechServices, text: str = "Tell me about mutability.") -> bytes:
    async with mock_http(fake) as http:
        stream = await tts.open_speech(http, text)
        return b"".join([chunk async for chunk in stream.chunks()])


async def speak_error(fake: FakeSpeechServices) -> ApiError:
    with pytest.raises(ApiError) as caught:
        await speak(fake)
    return caught.value


async def test_streams_the_audio_and_sends_the_documented_request():
    fake = FakeSpeechServices()

    audio = await speak(fake, "Tell me about mutability.")

    assert audio == FakeSpeechServices.AUDIO
    request = fake.calls("murf")[0]
    assert request.headers["api-key"] == "test-murf-key"
    assert json.loads(request.content) == {
        "text": "Tell me about mutability.",
        "voiceId": "en-US-natalie",
        "format": "MP3",
        "sampleRate": 24000,
        "locale": "en-US",
    }


async def test_chunks_arrive_in_order():
    fake = FakeSpeechServices()
    fake.murf_stream = Chunks(b"one-", b"two-", b"three")
    assert await speak(fake) == b"one-two-three"


async def test_markdown_is_not_read_aloud():
    fake = FakeSpeechServices()
    await speak(fake, "**Nice** answer! What does `yield` do?\n## Next")
    assert json.loads(fake.calls("murf")[0].content)["text"] == "Nice answer! What does yield do?\n Next"


@pytest.mark.parametrize("failure", [503, httpx.ConnectTimeout("slow"), httpx.ReadError("reset")])
async def test_a_temporary_failure_before_any_audio_is_retried(failure):
    fake = FakeSpeechServices()
    fake.fail("murf", failure)

    assert await speak(fake) == FakeSpeechServices.AUDIO
    assert len(fake.calls("murf")) == 2


async def test_gives_up_after_three_attempts():
    fake = FakeSpeechServices()
    fake.fail("murf", 500, 500, 500)

    error = await speak_error(fake)

    assert (error.status_code, error.error) == (502, "tts_error")
    assert len(fake.calls("murf")) == 3


@pytest.mark.parametrize(
    "status,http_status,code",
    [(403, 502, "tts_auth_failed"), (401, 502, "tts_auth_failed"), (402, 502, "tts_quota_exceeded"), (400, 502, "tts_error")],
)
async def test_errors_that_retrying_cannot_fix_are_not_retried(status, http_status, code):
    fake = FakeSpeechServices()
    fake.fail("murf", status)

    error = await speak_error(fake)

    assert (error.status_code, error.error) == (http_status, code)
    assert len(fake.calls("murf")) == 1


async def test_rate_limiting_and_timeouts_have_their_own_responses():
    limited = FakeSpeechServices()
    limited.fail("murf", 429, 429, 429)
    assert (await speak_error(limited)).error == "tts_rate_limited"

    slow = FakeSpeechServices()
    slow.fail("murf", *[httpx.ReadTimeout("slow")] * 3)
    assert (await speak_error(slow)).status_code == 504


async def test_an_empty_audio_response_counts_as_a_failure_and_is_retried():
    fake = FakeSpeechServices()
    fake.murf_stream = Chunks()

    error = await speak_error(fake)

    assert error.error == "tts_error"
    assert len(fake.calls("murf")) == 3


async def test_a_stream_that_breaks_after_audio_started_just_ends_early(caplog):
    caplog.set_level(logging.WARNING)
    fake = FakeSpeechServices()
    fake.murf_stream = Chunks(b"first-chunk", then_fail=True)

    audio = await speak(fake)

    assert audio == b"first-chunk"
    assert len(fake.calls("murf")) == 1  # nothing was retried: the listener already has part of it
    assert any(r.getMessage() == "speech stream broke" for r in caplog.records)


async def test_without_an_api_key_no_request_is_made(monkeypatch):
    fake = FakeSpeechServices()
    monkeypatch.setattr(settings, "murf_api_key", "")

    error = await speak_error(fake)

    assert (error.status_code, error.error) == (503, "tts_not_configured")
    assert fake.requests == []


async def test_the_api_key_is_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    fake = FakeSpeechServices()
    fake.fail("murf", 503, 403)

    await speak_error(fake)

    assert "test-murf-key" not in " ".join(str(r.__dict__) + r.getMessage() for r in caplog.records)
