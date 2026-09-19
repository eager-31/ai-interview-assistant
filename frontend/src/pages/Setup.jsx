import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { startInterview } from "../api";
import { describeError } from "../api/client";
import Alert from "../components/Alert";
import { ArrowIcon, FileIcon, UploadIcon } from "../components/Icons";
import { MAX_JOB_DESCRIPTION_CHARS, MAX_RESUME_BYTES, SUBJECT_SUGGESTIONS } from "../constants";

const formatSize = (bytes) => (bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`);

export default function Setup() {
  const navigate = useNavigate();
  const fileInput = useRef(null);
  const [subject, setSubject] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [resume, setResume] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [resumeProblem, setResumeProblem] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function chooseResume(file) {
    setResumeProblem(null);
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setResumeProblem("The resume must be a PDF file.");
      return;
    }
    if (file.size > MAX_RESUME_BYTES) {
      setResumeProblem(`The resume must be ${MAX_RESUME_BYTES / 1024 / 1024} MB or smaller.`);
      return;
    }
    setResume(file);
  }

  async function submit(event) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const started = await startInterview({ subject: subject.trim(), jobDescription: jobDescription.trim(), resume });
      navigate(`/interview/${started.session_id}`);
    } catch (err) {
      setError(describeError(err));
      setLoading(false);
    }
  }

  const tailored = Boolean(resume || jobDescription.trim());

  return (
    <form className="setup" onSubmit={submit} noValidate>
      <header className="page-head">
        <p className="text-eyebrow">New interview</p>
        <h1>What should we practise?</h1>
        <p className="text-lead">Five spoken questions. Add your resume or a job description and they will be tailored to it.</p>
      </header>

      {error && (
        <Alert title="Couldn't start the interview">
          {error.message}
        </Alert>
      )}

      <section className="card stack">
        <div className="field">
          <label className="field-label" htmlFor="subject">Subject</label>
          <input
            id="subject"
            className="input"
            value={subject}
            maxLength={100}
            placeholder="For example: Python, or React hooks"
            onChange={(e) => setSubject(e.target.value)}
            disabled={loading}
          />
          <div className="chips" role="group" aria-label="Suggested subjects">
            {SUBJECT_SUGGESTIONS.map((name) => (
              <button key={name} type="button" className="chip" aria-pressed={subject === name} onClick={() => setSubject(name)} disabled={loading}>
                {name}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="card stack">
        <div>
          <h3>Make it yours <span className="text-muted setup-optional">optional</span></h3>
          <p className="text-small">Both are optional. Use either one or both.</p>
        </div>

        <div className="field">
          <span className="field-label" id="resume-label">Resume (PDF)</span>
          {resume ? (
            <div className="file-chip">
              <FileIcon />
              <span className="file-name">{resume.name}</span>
              <span className="text-small">{formatSize(resume.size)}</span>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setResume(null)} disabled={loading}>Remove</button>
            </div>
          ) : (
            <label
              className="dropzone"
              data-active={dragging}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                chooseResume(e.dataTransfer.files?.[0]);
              }}
            >
              <UploadIcon />
              <strong>Drop a PDF here, or click to choose</strong>
              <span className="text-small">Up to 5 MB. It needs selectable text, so scanned images won't work.</span>
              <input
                ref={fileInput}
                type="file"
                accept="application/pdf,.pdf"
                className="visually-hidden"
                aria-labelledby="resume-label"
                onChange={(e) => {
                  chooseResume(e.target.files?.[0]);
                  e.target.value = "";
                }}
                disabled={loading}
              />
            </label>
          )}
          {resumeProblem && <span className="field-error" role="alert">{resumeProblem}</span>}
        </div>

        <div className="field">
          <label className="field-label" htmlFor="jd">Job description</label>
          <textarea
            id="jd"
            className="textarea"
            value={jobDescription}
            maxLength={MAX_JOB_DESCRIPTION_CHARS}
            placeholder="Paste the job description here"
            onChange={(e) => setJobDescription(e.target.value)}
            disabled={loading}
          />
          <span className="field-hint">{jobDescription.length.toLocaleString()} / {MAX_JOB_DESCRIPTION_CHARS.toLocaleString()}</span>
        </div>

        {tailored && (
          <p className="text-small">
            The text of your resume or job description is sent to Google's Gemini API to shape the questions. It is not saved.
          </p>
        )}
      </section>

      <div className="row setup-actions">
        <button type="submit" className="btn btn-primary btn-lg" disabled={loading || !subject.trim()} aria-busy={loading}>
          {loading ? "Preparing your interview" : <>Start interview <ArrowIcon /></>}
        </button>
        {loading && <span className="text-small" role="status">Reading your material and writing the first question. This can take up to 20 seconds.</span>}
      </div>
    </form>
  );
}
