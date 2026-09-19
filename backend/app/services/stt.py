import asyncio
import logging
import time

import httpx

from app.core.config import settings
from app.core.errors import ApiError, http_failure, speech_not_configured
from app.core.retry import call_with_retries

logger = logging.getLogger(__name__)

BASE_URL = "https://api.assemblyai.com/v2"
MAX_AUDIO_BYTES = 10 * 1024 * 1024
POLL_INTERVAL_SECONDS = 1.0
MAX_WAIT_SECONDS = 60.0


async def transcribe(http: httpx.AsyncClient, audio: bytes) -> str:
    """Upload a recording to AssemblyAI and return what was said, or "" if nothing was."""
    if not settings.assemblyai_api_key:
        raise speech_not_configured("stt")
    headers = {"authorization": settings.assemblyai_api_key}
    try:
        upload_url = await _upload(http, headers, audio)
        transcript_id = await _start(http, headers, upload_url)
        return await _wait_for_text(http, headers, transcript_id)
    except httpx.HTTPError as exc:
        raise http_failure("stt", exc) from exc


async def _upload(http: httpx.AsyncClient, headers: dict, audio: bytes) -> str:
    async def operation():
        response = await http.post(f"{BASE_URL}/upload", headers=headers, content=audio)
        response.raise_for_status()
        return response.json()["upload_url"]

    return await call_with_retries(operation)


async def _start(http: httpx.AsyncClient, headers: dict, upload_url: str) -> str:
    async def operation():
        response = await http.post(
            f"{BASE_URL}/transcript",
            headers=headers,
            json={"audio_url": upload_url, "language_detection": True},
        )
        response.raise_for_status()
        return response.json()["id"]

    return await call_with_retries(operation)


async def _wait_for_text(http: httpx.AsyncClient, headers: dict, transcript_id: str) -> str:
    async def poll():
        response = await http.get(f"{BASE_URL}/transcript/{transcript_id}", headers=headers)
        response.raise_for_status()
        return response.json()

    deadline = time.monotonic() + MAX_WAIT_SECONDS
    while time.monotonic() < deadline:
        transcript = await call_with_retries(poll)
        if transcript["status"] == "completed":
            return (transcript.get("text") or "").strip()
        if transcript["status"] == "error":
            # AssemblyAI reaches this state for files it can't read, so it is reported as a bad recording.
            logger.warning("transcription failed", extra={"upstream_error": transcript.get("error")})
            raise ApiError(422, "audio_unreadable", "The recording could not be processed. Try recording again.")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    raise ApiError(504, "stt_timeout", "The speech-to-text service took too long to respond. Try again.")
