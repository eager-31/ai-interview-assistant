import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { describeError } from "../api/client";
import Alert from "../components/Alert";
import { Logo } from "../components/Icons";
import { useAuth } from "../context/AuthContext";

// Decorative only: a fixed pseudo-random envelope, animated per bar in CSS.
const BARS = Array.from({ length: 76 }, (_, i) => ({
  height: 0.22 + 0.78 * Math.abs(Math.sin(i * 0.31) * Math.cos(i * 0.113 + 1)),
  delay: `${-((i * 7) % 11) * 0.3}s`,
  duration: `${2.4 + (i % 5) * 0.35}s`,
}));

function HeroBackdrop() {
  return (
    <div className="hero-backdrop" aria-hidden="true">
      <div className="hero-mesh" />
      <div className="hero-bars">
        {BARS.map((bar, i) => (
          <span key={i} style={{ "--h": bar.height, "--delay": bar.delay, "--duration": bar.duration }} />
        ))}
      </div>
      <div className="hero-veil" />
    </div>
  );
}

function AuthCard() {
  const { signIn, signUp, expired } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const creating = mode === "signup";

  async function submit(event) {
    event.preventDefault();
    setError(null);
    if (creating && password.length < 8) {
      setError("Use at least 8 characters for your password.");
      return;
    }
    setLoading(true);
    try {
      await (creating ? signUp : signIn)(email.trim(), password);
      navigate("/setup", { replace: true });
    } catch (err) {
      setError(describeError(err).message);
      setLoading(false);
    }
  }

  return (
    <div className="card auth-card">
      <div className="tabs" role="tablist" aria-label="Sign in or create an account">
        {[
          ["signin", "Sign in"],
          ["signup", "Create account"],
        ].map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={mode === value}
            className="tab"
            onClick={() => {
              setMode(value);
              setError(null);
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <form className="stack" onSubmit={submit} noValidate>
        {expired && !error && <Alert kind="info" title="You were signed out">Your session ended. Sign in to continue.</Alert>}
        {error && <Alert title={creating ? "Couldn't create the account" : "Couldn't sign in"}>{error}</Alert>}

        <div className="field">
          <label className="field-label" htmlFor="email">Email</label>
          <input id="email" className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="password">Password</label>
          <input
            id="password"
            className="input"
            type="password"
            autoComplete={creating ? "new-password" : "current-password"}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {creating && <span className="field-hint">At least 8 characters.</span>}
        </div>
        <button type="submit" className="btn btn-primary btn-lg" disabled={loading || !email || !password} aria-busy={loading}>
          {loading ? (creating ? "Creating account" : "Signing in") : creating ? "Create account" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

export default function Landing() {
  const { isSignedIn } = useAuth();
  if (isSignedIn) return <Navigate to="/setup" replace />;

  return (
    <div className="hero">
      <HeroBackdrop />
      <div className="container hero-inner">
        <div className="hero-copy">
          <div className="hero-brand"><Logo size={32} /><span>Interview Assistant</span></div>
          <p className="text-eyebrow">Voice interview practice</p>
          <h1 className="text-display">Practice the interview out loud.</h1>
          <p className="text-lead">
            Answer spoken questions, see a transcript of what you said, and get each answer scored on correctness, clarity and depth.
          </p>
          <ul className="hero-points">
            <li>Questions can be tailored to your resume or a job description</li>
            <li>The interviewer speaks; you answer with your microphone</li>
            <li>Scored feedback after five questions</li>
          </ul>
        </div>
        <AuthCard />
      </div>
    </div>
  );
}
