import { ApiFailure, getBaseUrl, getToken } from "./client";

// axios cannot stream a response body in the browser, so this one call uses fetch.

async function failureFrom(response) {
  let detail = null;
  try {
    detail = (await response.json()).detail;
  } catch {
    // not JSON; fall through to the generic message
  }
  return new ApiFailure({
    status: response.status,
    code: detail?.error ?? "error",
    message: detail?.message ?? "The audio could not be loaded.",
  });
}

const canStream = () => typeof MediaSource !== "undefined" && MediaSource.isTypeSupported("audio/mpeg");
const abortError = () => new DOMException("Aborted", "AbortError");

/**
 * Plays the interviewer's latest message through `audio`, starting as soon as the first bytes arrive.
 * Resolves when playback ends. `onHeaders` gets the progress headers; `onPlaying` fires when sound starts.
 */
export async function playInterviewerSpeech({ sessionId, audio, signal, onHeaders, onPlaying }) {
  let response;
  try {
    response = await fetch(`${getBaseUrl()}/api/interview/${sessionId}/speech`, {
      headers: { Authorization: `Bearer ${getToken()}` },
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiFailure({ status: 0, code: "network", message: "Can't reach the server." });
  }
  if (!response.ok) throw await failureFrom(response);

  onHeaders?.({
    questionNumber: Number(response.headers.get("X-Question-Number")) || null,
    complete: response.headers.get("X-Interview-Complete") === "true",
  });

  return canStream()
    ? streamIntoAudio(response, audio, signal, onPlaying)
    : playWholeFile(response, audio, signal, onPlaying);
}

function streamIntoAudio(response, audio, signal, onPlaying) {
  return new Promise((resolve, reject) => {
    const mediaSource = new MediaSource();
    const url = URL.createObjectURL(mediaSource);
    const reader = response.body.getReader();

    const cleanup = () => {
      audio.removeEventListener("ended", onEnded);
      audio.removeEventListener("error", onAudioError);
      signal?.removeEventListener("abort", onAbort);
      URL.revokeObjectURL(url);
    };
    const onEnded = () => {
      cleanup();
      resolve();
    };
    const onAudioError = () => {
      cleanup();
      reject(new Error("The audio could not be decoded."));
    };
    const onAbort = () => {
      reader.cancel().catch(() => {});
      audio.pause();
      cleanup();
      reject(abortError());
    };

    audio.addEventListener("ended", onEnded);
    audio.addEventListener("error", onAudioError);
    signal?.addEventListener("abort", onAbort);
    audio.src = url;

    mediaSource.addEventListener(
      "sourceopen",
      async () => {
        const buffer = mediaSource.addSourceBuffer("audio/mpeg");
        const append = (chunk) =>
          new Promise((done, fail) => {
            buffer.addEventListener("updateend", done, { once: true });
            buffer.addEventListener("error", () => fail(new Error("The audio could not be decoded.")), { once: true });
            buffer.appendBuffer(chunk);
          });

        try {
          let started = false;
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            await append(value);
            if (!started) {
              started = true;
              await audio.play();
              onPlaying?.();
            }
          }
          mediaSource.endOfStream();
        } catch (error) {
          cleanup();
          reject(error);
        }
      },
      { once: true },
    );
  });
}

async function playWholeFile(response, audio, signal, onPlaying) {
  const url = URL.createObjectURL(await response.blob());
  try {
    audio.src = url;
    const finished = new Promise((resolve, reject) => {
      audio.addEventListener("ended", resolve, { once: true });
      audio.addEventListener("error", () => reject(new Error("The audio could not be decoded.")), { once: true });
      signal?.addEventListener("abort", () => {
        audio.pause();
        reject(abortError());
      });
    });
    await audio.play();
    onPlaying?.();
    await finished;
  } finally {
    URL.revokeObjectURL(url);
  }
}
