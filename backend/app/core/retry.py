import logging

import httpx
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_WAIT = wait_exponential(multiplier=0.5, max=4)


def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)  # includes timeouts


def _log_retry(state: RetryCallState) -> None:
    logger.warning("retrying external call", extra={"attempt": state.attempt_number, "error": repr(state.outcome.exception())})


# Speech-to-text and text-to-speech calls are safe to repeat: they don't change
# anything on our side. The Gemini call is the opposite. An agent turn that is
# retried can append the same messages to the conversation twice, so it is never
# retried (see llm_errors).
async def call_with_retries(operation):
    async for attempt in AsyncRetrying(
        retry=retry_if_exception(is_transient),
        stop=stop_after_attempt(MAX_ATTEMPTS),
        wait=RETRY_WAIT,
        before_sleep=_log_retry,
        reraise=True,
    ):
        with attempt:
            return await operation()
