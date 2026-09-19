import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getFeedback, getInterview } from "../api";
import { describeError } from "../api/client";
import Alert from "../components/Alert";
import { ArrowIcon } from "../components/Icons";
import ScoreRing from "../components/ScoreRing";
import ScoresChart, { CRITERIA } from "../components/ScoresChart";
import { TOTAL_QUESTIONS } from "../constants";
import { formatDate, formatDuration, formatScore, scoreWord } from "../utils/format";

export default function Results() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [state, setState] = useState({ status: "loading" }); // loading | generating | ready | error
  const [interview, setInterview] = useState(null);

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const detail = await getInterview(id);
      setInterview(detail);
      if (detail.status === "completed" && !detail.feedback) {
        setState({ status: "generating" });
        const feedback = await getFeedback(id);
        setInterview({ ...detail, feedback });
      }
      setState({ status: "ready" });
    } catch (error) {
      setState({ status: "error", error: describeError(error) });
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (!interview && state.status !== "error") return <ResultsSkeleton note={state.status === "generating" ? "Writing your feedback" : null} />;
  if (!interview) {
    return (
      <Alert title="Couldn't open this interview" actions={[{ label: "Try again", onClick: load }, { label: "Back to history", onClick: () => navigate("/history") }]}>
        {state.error.message}
      </Alert>
    );
  }

  const { feedback } = interview;
  const answered = interview.turns.filter((turn) => turn.answer_text);
  const scored = answered.filter((turn) => turn.correctness != null);
  const finished = interview.status === "completed";

  return (
    <div className="results stack">
      <header className="page-head">
        <p className="text-eyebrow">{interview.subject}</p>
        <h1>{finished ? "Your feedback" : "Interview in progress"}</h1>
        <p className="text-small">
          {formatDate(interview.started_at)}
          {interview.completed_at && ` · ${formatDuration(interview.started_at, interview.completed_at)}`}
          {` · ${answered.length} of ${TOTAL_QUESTIONS} answered`}
        </p>
      </header>

      {state.status === "error" && (
        <Alert title="Couldn't write the feedback" actions={[{ label: "Try again", onClick: load }]}>
          {state.error.message} Your answers are saved.
        </Alert>
      )}

      {state.status === "generating" && <ResultsSkeleton note="Writing your feedback. This usually takes 10 to 20 seconds." />}

      {!finished && (
        <Alert kind="info" title="Feedback appears once all five questions are answered" actions={[{ label: "Continue interview", onClick: () => navigate(`/interview/${id}`) }]}>
          You can pick up where you left off while the session is still open.
        </Alert>
      )}

      {feedback && (
        <>
          <section className="card summary">
            <ScoreRing value={feedback.score} label="Overall score" />
            <div className="summary-body">
              <p className="text-eyebrow">Overall</p>
              <h2>{scoreWord(feedback.score)}</h2>
              <p className="text-small">
                {scored.length > 0
                  ? `Worked out from the scores of ${scored.length} answered question${scored.length === 1 ? "" : "s"}.`
                  : "None of the answers could be scored, so this is the model's overall judgement."}
              </p>
            </div>
            <div className="meters">
              {CRITERIA.map((criterion) => {
                const value = feedback[criterion.key];
                return (
                  <div key={criterion.key} className="meter">
                    <div className="meter-head">
                      <span>{criterion.label}</span>
                      <strong>{formatScore(value)}{value != null && <span className="text-muted"> / 5</span>}</strong>
                    </div>
                    <div className="meter-track">
                      <div className="meter-fill" style={{ width: `${((value ?? 0) / 5) * 100}%`, background: `var(${criterion.token})` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {scored.length > 0 && (
            <section className="card stack">
              <h3>Score by question</h3>
              <ScoresChart turns={scored} />
            </section>
          )}

          <div className="feedback-grid">
            <section className="card stack">
              <h3>What went well</h3>
              <p className="prose">{feedback.feedback}</p>
            </section>
            <section className="card stack">
              <h3>What to work on</h3>
              <p className="prose">{feedback.areas_of_improvement}</p>
            </section>
          </div>
        </>
      )}

      <section className="card stack">
        <h3>Transcript</h3>
        <ol className="transcript">
          {interview.turns.map((turn) => (
            <li key={turn.question_number}>
              <p className="text-eyebrow">Question {turn.question_number}</p>
              <p className="exchange-q">{turn.question_text}</p>
              {turn.answer_text ? <p className="exchange-a">{turn.answer_text}</p> : <p className="text-muted">Not answered yet.</p>}
              {turn.correctness != null && (
                <>
                  <ul className="score-chips" aria-label="Scores for this answer">
                    {CRITERIA.map((criterion) => (
                      <li key={criterion.key}>
                        <span className="legend-swatch" style={{ background: `var(${criterion.token})` }} aria-hidden="true" />
                        {criterion.label} <strong>{turn[criterion.key]}</strong>
                      </li>
                    ))}
                  </ul>
                  {turn.score_comment && <p className="text-small">{turn.score_comment}</p>}
                </>
              )}
            </li>
          ))}
        </ol>
      </section>

      <div className="row">
        <Link to="/setup" className="btn btn-primary">Start another interview <ArrowIcon /></Link>
        <Link to="/history" className="btn btn-secondary">All interviews</Link>
      </div>
    </div>
  );
}

function ResultsSkeleton({ note }) {
  return (
    <div className="results stack" aria-busy="true" aria-label="Loading">
      <div className="skeleton skeleton-title" />
      <section className="card summary">
        <div className="skeleton" style={{ width: 132, height: 132, borderRadius: "50%" }} />
        <div className="summary-body">
          <div className="skeleton skeleton-text" style={{ width: "40%" }} />
          <div className="skeleton skeleton-title" />
        </div>
        <div className="meters">
          {[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 34 }} />)}
        </div>
      </section>
      {note && <p className="text-small" role="status">{note}</p>}
      <div className="card"><div className="skeleton" style={{ height: 240 }} /></div>
    </div>
  );
}
