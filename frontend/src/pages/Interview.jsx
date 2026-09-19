import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getInterview, submitAudio } from "../api";
import { ApiFailure, describeError } from "../api/client";
import { playInterviewerSpeech } from "../api/speech";
import Alert from "../components/Alert";
import { ArrowIcon, MicIcon, PlayIcon, ReplayIcon, StopIcon } from "../components/Icons";
import Waveform from "../components/Waveform";
import { MIN_RECORDING_MS, TOTAL_QUESTIONS } from "../constants";
import { extensionFor, useRecorder } from "../hooks/useRecorder";
import { formatClock } from "../utils/format";

// Problems where sending the same recording again cannot help.
const NOT_RETRYABLE = new Set(["no_speech_detected", "audio_empty", "audio_unreadable", "audio_too_large", "interview_completed", "session_not_found"]);

export default function Interview() {
  const { id } = useParams();
  const navigate = useNavigate();

  const audioRef = useRef(null);
  const audioContextRef = useRef(null);
  const speechAnalyserRef = useRef(null);
  const abortRef = useRef(null);
  const pendingRef = useRef(null);
  const mounted = useRef(false);
  const spokeFirst = useRef(false);

  const [load, setLoad] = useState({ status: "loading" });
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [questionNumber, setQuestionNumber] = useState(1);
  const [complete, setComplete] = useState(false);
  const [exchanges, setExchanges] = useState([]);
  const [heard, setHeard] = useState(null);
  const [phase, setPhase] = useState("ready"); // ready | speaking | recording | processing
  const [problem, setProblem] = useState(null);
  const [notice, setNotice] = useState(null);
  const [speechAnalyser, setSpeechAnalyser] = useState(null);

  const getAudioContext = useCallback(() => {
    audioContextRef.current ??= new (window.AudioContext || window.webkitAudioContext)();
    return audioContextRef.current;
  }, []);

  // Lets the waveform follow the interviewer's voice. Routing an <audio> element through a
  // suspended context would silence it, so this only happens once the context is running.
  const ensureSpeechGraph = useCallback(async () => {
    if (speechAnalyserRef.current || !audioRef.current) return;
    const context = getAudioContext();
    await context.resume().catch(() => {});
    if (context.state !== "running") return;
    const source = context.createMediaElementSource(audioRef.current);
    const node = context.createAnalyser();
    node.fftSize = 512;
    node.smoothingTimeConstant = 0.8;
    source.connect(node);
    node.connect(context.destination);
    speechAnalyserRef.current = node;
    setSpeechAnalyser(node);
  }, [getAudioContext]);

  const speak = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setProblem(null);
    setNotice(null);
    setPhase("speaking");
    try {
      await ensureSpeechGraph();
      await playInterviewerSpeech({
        sessionId: id,
        audio: audioRef.current,
        signal: controller.signal,
        // The progress comes from the X-Question-Number header the speech response carries.
        onHeaders: ({ questionNumber: number, complete: finished }) => {
          if (number) setQuestionNumber(number);
          if (finished) setComplete(true);
        },
      });
    } catch (error) {
      if (error.name === "AbortError") return;
      setNotice(
        error.name === "NotAllowedError"
          ? "Your browser blocked automatic playback. Press Play to hear the question."
          : `The audio couldn't be played${error instanceof ApiFailure ? `: ${error.message}` : "."} You can read the question below.`,
      );
    }
    if (abortRef.current === controller) setPhase("ready");
  }, [id, ensureSpeechGraph]);

  const send = useCallback(
    async (recorded) => {
      setPhase("processing");
      setProblem(null);
      pendingRef.current = recorded;
      try {
        const result = await submitAudio(id, recorded.blob, `answer.${extensionFor(recorded.mimeType)}`);
        pendingRef.current = null;
        setHeard(result.transcript);
        setExchanges((previous) => [...previous, { question: message, answer: result.transcript }]);
        setMessage(result.message);
        setQuestionNumber(result.question_number);
        setComplete(result.interview_complete);
        await speak();
      } catch (error) {
        const info = describeError(error);
        setProblem({
          title: info.code === "no_speech_detected" ? "We couldn't hear you" : "Your answer wasn't sent",
          message: info.message,
          retry: !NOT_RETRYABLE.has(info.code) && info.status !== 401,
          expired: info.code === "session_not_found",
        });
        setPhase("ready");
      }
    },
    [id, message, speak],
  );

  const recorder = useRecorder({ getAudioContext, onMaxLength: () => finishRecording() });

  async function startRecording() {
    abortRef.current?.abort();
    audioRef.current?.pause();
    setProblem(null);
    setNotice(null);
    setHeard(null);
    pendingRef.current = null;
    try {
      await recorder.start();
      setPhase("recording");
    } catch (error) {
      setProblem({ title: "Microphone problem", message: error.message });
      setPhase("ready");
    }
  }

  async function finishRecording() {
    let recorded;
    try {
      recorded = await recorder.stop();
    } catch {
      return; // already stopped
    }
    if (recorded.durationMs < MIN_RECORDING_MS) {
      setProblem({ title: "That was too short", message: "Hold on a little longer, then press Stop when you've finished your answer." });
      setPhase("ready");
      return;
    }
    await send(recorded);
  }

  function cancelRecording() {
    recorder.cancel();
    setPhase("ready");
  }

  useEffect(() => {
    let cancelled = false;
    getInterview(id)
      .then((interview) => {
        if (cancelled) return;
        if (interview.status === "completed") {
          navigate(`/interviews/${id}`, { replace: true });
          return;
        }
        const current = interview.turns[interview.turns.length - 1];
        setSubject(interview.subject);
        setMessage(current.question_text);
        setQuestionNumber(current.question_number);
        setExchanges(interview.turns.filter((turn) => turn.answer_text).map((turn) => ({ question: turn.question_text, answer: turn.answer_text })));
        setLoad({ status: "ready" });
      })
      .catch((error) => !cancelled && setLoad({ status: "error", error: describeError(error) }));
    return () => {
      cancelled = true;
    };
  }, [id, navigate]);

  useEffect(() => {
    if (load.status === "ready" && !spokeFirst.current) {
      spokeFirst.current = true;
      speak();
    }
  }, [load.status, speak]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      spokeFirst.current = false;
      abortRef.current?.abort();
      const context = audioContextRef.current;
      // React re-runs effects once in development; only close the context if we really left the page.
      setTimeout(() => {
        if (!mounted.current) context?.close().catch(() => {});
      }, 0);
    };
  }, []);

  if (load.status === "loading") return <InterviewSkeleton />;
  if (load.status === "error") {
    return (
      <div className="stack">
        <Alert title="Couldn't open this interview" actions={[{ label: "Try again", onClick: () => window.location.reload() }, { label: "Back to history", onClick: () => navigate("/history") }]}>
          {load.error.message}
        </Alert>
      </div>
    );
  }

  const recording = phase === "recording";
  const processing = phase === "processing";
  const speaking = phase === "speaking";
  const waveMode = recording ? "listening" : speaking ? "speaking" : processing ? "thinking" : "idle";
  const waveAnalyser = recording ? recorder.analyser : speaking ? speechAnalyser : null;
  const status = complete && !speaking ? "Interview complete" : recording ? `Recording ${formatClock(recorder.elapsed)}` : speaking ? "Natalie is speaking" : processing ? "Transcribing and thinking" : "Your turn";
  const current = complete ? TOTAL_QUESTIONS + 1 : questionNumber;

  const problemActions = [];
  if (problem?.retry && pendingRef.current) problemActions.push({ label: "Send again", onClick: () => send(pendingRef.current) });
  if (problem?.expired) problemActions.push({ label: "Start a new interview", onClick: () => navigate("/setup") });

  return (
    <div className="interview stack">
      <header className="interview-head">
        <div>
          <p className="text-eyebrow">{subject}</p>
          <h1 className="interview-title">{complete ? "All questions answered" : `Question ${questionNumber} of ${TOTAL_QUESTIONS}`}</h1>
        </div>
        <div className="steps" role="img" aria-label={`Question ${Math.min(questionNumber, TOTAL_QUESTIONS)} of ${TOTAL_QUESTIONS}`}>
          {Array.from({ length: TOTAL_QUESTIONS }, (_, i) => (
            <span key={i} className="step" data-state={i + 1 < current ? "done" : i + 1 === current ? "current" : "todo"} />
          ))}
        </div>
      </header>

      <section className="card stage" aria-label="Interview">
        <p className="stage-status" role="status" data-phase={phase}>
          <span className="stage-dot" aria-hidden="true" />
          {status}
        </p>
        <blockquote className="stage-message" aria-live="polite">{message}</blockquote>
        <Waveform analyser={waveAnalyser} mode={waveMode} />

        {heard && !recording && (
          <p className="heard"><span className="text-eyebrow">What we heard</span>{heard}</p>
        )}

        {notice && <Alert kind="info">{notice}</Alert>}
        {problem && <Alert title={problem.title} actions={problemActions}>{problem.message}</Alert>}

        <div className="controls">
          {complete ? (
            <button type="button" className="btn btn-primary btn-lg" onClick={() => navigate(`/interviews/${id}`)}>
              See your feedback <ArrowIcon />
            </button>
          ) : recording ? (
            <>
              <button type="button" className="btn btn-primary btn-lg is-recording" onClick={finishRecording}>
                <StopIcon /> Stop and send
              </button>
              <button type="button" className="btn btn-ghost" onClick={cancelRecording}>Cancel</button>
            </>
          ) : (
            <button type="button" className="btn btn-primary btn-lg" onClick={startRecording} disabled={processing} aria-busy={processing}>
              {processing ? "Sending your answer" : <><MicIcon /> {speaking ? "Answer now" : "Start answering"}</>}
            </button>
          )}
          {!recording && !processing && (
            <button type="button" className="btn btn-secondary" onClick={speak} disabled={speaking}>
              {notice?.startsWith("Your browser blocked") ? <PlayIcon /> : <ReplayIcon />}
              {notice?.startsWith("Your browser blocked") ? "Play question" : complete ? "Replay" : "Replay question"}
            </button>
          )}
        </div>
      </section>

      {exchanges.length > 0 && (
        <details className="card so-far">
          <summary>Conversation so far ({exchanges.length})</summary>
          <ol className="exchanges">
            {exchanges.map((exchange, index) => (
              <li key={index}>
                <p className="exchange-q">{exchange.question}</p>
                <p className="exchange-a">{exchange.answer}</p>
              </li>
            ))}
          </ol>
        </details>
      )}

      <audio ref={audioRef} preload="none" />
    </div>
  );
}

function InterviewSkeleton() {
  return (
    <div className="interview stack" aria-busy="true" aria-label="Loading interview">
      <div className="skeleton skeleton-title" />
      <div className="card stage">
        <div className="skeleton skeleton-text" style={{ width: "30%" }} />
        <div className="skeleton skeleton-text" style={{ width: "95%" }} />
        <div className="skeleton skeleton-text" style={{ width: "80%" }} />
        <div className="skeleton" style={{ height: 96, marginTop: 16 }} />
      </div>
    </div>
  );
}
