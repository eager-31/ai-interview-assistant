import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getHistory } from "../api";
import { describeError } from "../api/client";
import Alert from "../components/Alert";
import { ArrowIcon } from "../components/Icons";
import { formatDate, formatDuration, scoreWord } from "../utils/format";

function HistoryCard({ interview }) {
  const done = interview.status === "completed";
  return (
    <Link to={`/interviews/${interview.id}`} className="card card-interactive history-card">
      <div className="row history-top">
        <span className="badge badge-accent">{interview.subject}</span>
        <span className={`badge ${done ? "badge-success" : ""}`}>{done ? "Completed" : "In progress"}</span>
      </div>
      {interview.score != null ? (
        <p className="history-score">
          <span className="history-score-number">{interview.score}</span>
          <span className="text-muted"> / 5</span>
          <span className="history-score-word">{scoreWord(interview.score)}</span>
        </p>
      ) : (
        <p className="history-score history-score-empty">{done ? "Feedback not written yet" : "Not finished"}</p>
      )}
      <p className="text-small">
        {formatDate(interview.started_at)}
        {interview.completed_at && ` · ${formatDuration(interview.started_at, interview.completed_at)}`}
      </p>
    </Link>
  );
}

function HistorySkeleton() {
  return (
    <div className="history-grid" aria-busy="true" aria-label="Loading your interviews">
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div className="skeleton" style={{ width: 84, height: 22, borderRadius: 999 }} />
            <div className="skeleton" style={{ width: 70, height: 22, borderRadius: 999 }} />
          </div>
          <div className="skeleton skeleton-title" style={{ marginBlock: 20, width: "35%" }} />
          <div className="skeleton skeleton-text" style={{ width: "55%" }} />
        </div>
      ))}
    </div>
  );
}

export default function History() {
  const [state, setState] = useState({ status: "loading" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      setState({ status: "ready", interviews: await getHistory() });
    } catch (error) {
      setState({ status: "error", error: describeError(error) });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="stack">
      <header className="page-head">
        <p className="text-eyebrow">History</p>
        <h1>Your interviews</h1>
      </header>

      {state.status === "loading" && <HistorySkeleton />}

      {state.status === "error" && (
        <Alert title="Couldn't load your interviews" actions={[{ label: "Try again", onClick: load }]}>
          {state.error.message}
        </Alert>
      )}

      {state.status === "ready" && state.interviews.length === 0 && (
        <div className="card empty">
          <h3>No interviews yet</h3>
          <p className="text-small">Your first one will show up here with its score and transcript.</p>
          <Link to="/setup" className="btn btn-primary">Start an interview <ArrowIcon /></Link>
        </div>
      )}

      {state.status === "ready" && state.interviews.length > 0 && (
        <div className="history-grid">
          {state.interviews.map((interview) => <HistoryCard key={interview.id} interview={interview} />)}
        </div>
      )}
    </div>
  );
}
