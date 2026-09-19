import { api } from "./client";

export async function register(email, password) {
  await api.post("/api/auth/register", { email, password });
}

export async function login(email, password) {
  const { data } = await api.post("/api/auth/login", { email, password });
  return data.access_token;
}

export async function startInterview({ subject, jobDescription, resume }) {
  const form = new FormData();
  form.append("subject", subject);
  if (jobDescription) form.append("job_description", jobDescription);
  if (resume) form.append("resume", resume);
  const { data } = await api.post("/api/interview/start", form);
  return data;
}

export async function submitAudio(sessionId, blob, filename) {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("audio", blob, filename);
  const { data } = await api.post("/api/interview/submit-answer-audio", form);
  return data;
}

export async function getHistory() {
  const { data } = await api.get("/api/interview/history");
  return data;
}

export async function getInterview(sessionId) {
  const { data } = await api.get(`/api/interview/${sessionId}`);
  return data;
}

// Feedback costs a model call, so overlapping requests for one interview share a single request.
const pendingFeedback = new Map();

export function getFeedback(sessionId) {
  if (!pendingFeedback.has(sessionId)) {
    const request = api
      .post("/api/interview/get-feedback", { session_id: sessionId })
      .then(({ data }) => data)
      .finally(() => pendingFeedback.delete(sessionId));
    pendingFeedback.set(sessionId, request);
  }
  return pendingFeedback.get(sessionId);
}
