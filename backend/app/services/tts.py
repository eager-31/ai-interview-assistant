import logging
import re

import httpx

from app.core.config import settings
from app.core.errors import http_failure, speech_not_configured
from app.core.retry import call_with_retries

logger = logging.getLogger(__name__)

URL = "https://global.api.murf.ai/v1/speech/stream"
VOICE_ID = "en-US-natalie"


def _speakable(text: str) -> str:
    # Gemini sometimes answers with markdown (backticks, bold, headings), which a voice would read out loud.
    return re.sub(r"[*`#]", "", text).strip()


class SpeechStream:
    """Audio from Murf that has already started arriving, so the caller knows the request worked."""

    def __init__(self, response: httpx.Response, first_chunk: bytes, rest):
        self._response = response
        self._first_chunk = first_chunk
        self._rest = rest

    async def chunks(self):
        try:
            yield self._first_chunk
            async for chunk in self._rest:
                yield chunk
        except httpx.HTTPError as exc:
            # The listener already has part of the audio, so it can't be restarted; it simply ends early.
            logger.warning("speech stream broke", extra={"error": repr(exc)})
        finally:
            await self._response.aclose()


async def open_speech(http: httpx.AsyncClient, text: str) -> SpeechStream:
    """Start streaming `text` as speech. Failures before the first bytes are retried, then raised as ApiError."""
    if not settings.murf_api_key:
        raise speech_not_configured("tts")
    payload = {"text": _speakable(text), "voiceId": VOICE_ID, "format": "MP3", "sampleRate": 24000, "locale": "en-US"}

    async def operation():
        request = http.build_request("POST", URL, headers={"api-key": settings.murf_api_key}, json=payload)
        response = await http.send(request, stream=True)
        try:
            response.raise_for_status()
            chunks = response.aiter_bytes()
            first_chunk = await anext(chunks, b"")
            if not first_chunk:
                raise httpx.ReadError("Murf returned no audio", request=request)
        except BaseException:
            await response.aclose()
            raise
        return SpeechStream(response, first_chunk, chunks)

    try:
        return await call_with_retries(operation)
    except httpx.HTTPError as exc:
        raise http_failure("tts", exc) from exc
