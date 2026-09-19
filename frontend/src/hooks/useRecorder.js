import { useCallback, useEffect, useRef, useState } from "react";
import { MAX_RECORDING_SECONDS } from "../constants";

const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

export class MicrophoneError extends Error {}

function explain(error) {
  if (error?.name === "NotAllowedError") {
    return "Microphone access was blocked. Allow it in your browser's address bar, then try again.";
  }
  if (error?.name === "NotFoundError") return "No microphone was found. Connect one and try again.";
  return "The microphone could not be started.";
}

/** Filename extension that matches what the browser actually recorded. */
export function extensionFor(mimeType) {
  if (mimeType.includes("mp4")) return "m4a";
  if (mimeType.includes("ogg")) return "ogg";
  return "webm";
}

export function useRecorder({ getAudioContext, onMaxLength }) {
  const [recording, setRecording] = useState(false);
  const [analyser, setAnalyser] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const session = useRef({});
  const onMaxLengthRef = useRef(onMaxLength);
  onMaxLengthRef.current = onMaxLength;

  const teardown = useCallback(() => {
    const current = session.current;
    clearInterval(current.timer);
    current.stream?.getTracks().forEach((track) => track.stop());
    current.source?.disconnect();
    session.current = {};
    setAnalyser(null);
    setRecording(false);
  }, []);

  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      throw new MicrophoneError("Recording is not supported here. Use a current browser on https or localhost.");
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (error) {
      throw new MicrophoneError(explain(error));
    }

    const mimeType = MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type));
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks = [];
    recorder.ondataavailable = (event) => event.data.size && chunks.push(event.data);

    const context = getAudioContext();
    await context.resume().catch(() => {});
    const source = context.createMediaStreamSource(stream);
    const node = context.createAnalyser();
    node.fftSize = 512;
    node.smoothingTimeConstant = 0.75;
    source.connect(node); // not connected to the speakers, so the candidate doesn't hear themselves

    const startedAt = performance.now();
    const timer = setInterval(() => {
      const seconds = (performance.now() - startedAt) / 1000;
      setElapsed(seconds);
      if (seconds >= MAX_RECORDING_SECONDS) onMaxLengthRef.current?.();
    }, 200);

    session.current = { stream, recorder, chunks, source, startedAt, timer };
    recorder.start(250);
    setElapsed(0);
    setAnalyser(node);
    setRecording(true);
  }, [getAudioContext]);

  const stop = useCallback(
    () =>
      new Promise((resolve, reject) => {
        const current = session.current;
        if (!current.recorder || current.recorder.state === "inactive") {
          reject(new MicrophoneError("Not recording."));
          return;
        }
        current.recorder.onstop = () => {
          const durationMs = performance.now() - current.startedAt;
          const type = current.recorder.mimeType || current.chunks[0]?.type || "audio/webm";
          const blob = new Blob(current.chunks, { type });
          teardown();
          resolve({ blob, durationMs, mimeType: type });
        };
        current.recorder.stop();
      }),
    [teardown],
  );

  const cancel = useCallback(() => {
    const { recorder } = session.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    teardown();
  }, [teardown]);

  useEffect(() => cancel, [cancel]);

  return { start, stop, cancel, recording, analyser, elapsed };
}
