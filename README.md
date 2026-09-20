# AI Interview Assistant

**Practice interviews out loud. An AI interviewer asks the questions, you answer with your voice, and every answer is scored.**

## Live Demo

[🚀 Try AI Interview Assistant](https://ai-interview-assistant-seven-eta.vercel.app/)

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Redis%20checkpoints-1C3C3C)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-Redis%20Cloud-DC382D?logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-multi--stage-2496ED?logo=docker&logoColor=white)

---

## Overview

Most interview practice tools are text chats. Real interviews are spoken, so this project practises the real thing:

1. You pick a subject (and optionally upload your resume or paste a job description).
2. **Natalie**, the AI interviewer, asks five questions and speaks them aloud.
3. You answer with your microphone. Your speech is transcribed, so you can see exactly what was heard.
4. Each answer is scored on **correctness, clarity and depth**.
5. After question five you get written feedback, a score chart and a full transcript. Past interviews are saved in your history.

It is a full-stack project: a React single-page app, an async FastAPI backend, an LLM agent with persistent conversation state, and three external AI services (Gemini, AssemblyAI, Murf).

## Key features

| Area | What it does |
|---|---|
| Voice interview | Record in the browser (MediaRecorder), transcribe with AssemblyAI, hear the interviewer through Murf text-to-speech streamed as it is generated |
| Live waveform | Web Audio `AnalyserNode` draws the microphone level while you speak and the interviewer's voice while it speaks |
| Tailored questions | Upload a resume PDF and/or paste a job description; Gemini summarises it and the interviewer uses it |
| Per-answer scoring | Structured Gemini output gives 1 to 5 for correctness, clarity and depth, plus a one-line comment |
| Reproducible final score | The overall score and averages are calculated in code from the stored per-answer scores, not left to the LLM |
| Accounts | Register and log in with bcrypt-hashed passwords and JWT access tokens; every interview belongs to one user |
| History and results | Every interview, transcript and feedback is stored in PostgreSQL and shown as cards, a score ring and a bar chart |
| Resilient by design | Distinct error responses for Gemini, AssemblyAI, Murf, Redis and PostgreSQL failures; retries only where they are safe |

## Architecture

```
                         ┌──────────────────────────────────────────┐
                         │                 Browser                  │
                         │  React + Vite SPA (hosted on Vercel)     │
                         │  MediaRecorder · Web Audio · axios/fetch │
                         └───────────────────┬──────────────────────┘
                                             │ HTTPS  (JWT in Authorization header)
                                             ▼
                         ┌──────────────────────────────────────────┐
                         │   FastAPI backend (Docker, on Render)    │
                         │   auth · interview routes · rate limit   │
                         │   error mapping · JSON logs              │
                         └───┬───────────┬─────────────┬────────────┘
                             │           │             │
        ┌────────────────────┘           │             └──────────────────────┐
        ▼                                ▼                                    ▼
┌────────────────┐             ┌───────────────────┐           ┌───────────────────────────┐
│  Redis Cloud   │             │  PostgreSQL       │           │  External AI services     │
│  live state    │             │  (Neon)           │           │                           │
│  · session hash│             │  permanent record │           │  Gemini      questions,   │
│  · LangGraph   │             │  · users          │           │              scoring,     │
│    checkpoints │             │  · interviews     │           │              feedback     │
│  (expires in   │             │  · turns + scores │           │  AssemblyAI  speech → text│
│   2 hours)     │             │  · feedback       │           │  Murf        text → speech│
└────────────────┘             └───────────────────┘           └───────────────────────────┘
```

**Why two data stores?** Redis holds the *live* interview (the agent's conversation memory and a small session hash) because it is fast and can expire on its own. PostgreSQL holds the *permanent* record (users, transcripts, scores, feedback) so history survives Redis expiry and restarts.

## How an interview works

```
Setup screen ──► POST /start ──► (resume text ──► Gemini summary) ──► Gemini asks Q1
                                   │
                                   └─► saved in PostgreSQL + Redis session created

Record answer ──► POST /submit-answer-audio
                     ├─ AssemblyAI transcribes the recording
                     ├─ Gemini writes the next question   ┐ run at the same time
                     ├─ Gemini scores the answer          ┘
                     └─ saved in PostgreSQL, counters updated in Redis

GET /{id}/speech ──► Murf streams the interviewer's reply ──► browser plays it as it arrives

After Q5 ──► POST /get-feedback ──► Gemini writes the feedback text,
             averages and overall score are computed in code ──► saved once
```

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, Pydantic v2, pydantic-settings, Uvicorn |
| AI orchestration | LangChain (`create_agent`), LangGraph, `langgraph-checkpoint-redis` |
| LLM | Google Gemini (model set by `GEMINI_MODEL`) via `langchain-google-genai` |
| Speech | AssemblyAI (speech-to-text), Murf (text-to-speech), both over plain `httpx` |
| Data | PostgreSQL via async SQLAlchemy 2.0 + asyncpg, migrations with Alembic; Redis (with RedisJSON and RediSearch) |
| Security | bcrypt, PyJWT (HS256), slowapi rate limiting, CORS allow-list |
| Resilience | tenacity retries, structured JSON logging |
| Frontend | React 19, Vite, React Router, axios, Recharts, plain CSS design system |
| Packaging | Docker (backend image, multi-stage frontend image served by nginx) |
| Hosting | Vercel (frontend), Render (backend container), Neon (PostgreSQL), Redis Cloud (Redis) |

## Important technical decisions

| Decision | Why |
|---|---|
| **Async FastAPI end to end** | A request spends most of its time waiting on other services (LLM, STT, TTS, databases). Async lets one process serve other users during those waits. CPU-heavy work (bcrypt, PDF parsing) is pushed to a thread. |
| **LangGraph with a Redis checkpointer** | The interviewer must remember the whole conversation. Each interview is one LangGraph *thread* keyed by its `session_id`, so state is persisted per interview and two users can never share it. |
| **Redis for live state, PostgreSQL for history** | Live state is temporary and hot; history is permanent and relational. Each store does the job it is good at. |
| **Scoring is a separate Gemini call, run in parallel** | The reply and the score do not depend on each other, so the user does not wait for both in sequence. A failed score never fails the interview turn. |
| **Overall score computed in code** | An LLM's "overall 4 out of 5" is not reproducible. Averaging the stored per-answer scores is. |
| **Gemini is never retried automatically** | A retried agent turn can add the same messages to the conversation twice. Speech calls are stateless, so they *are* retried (3 attempts, exponential backoff, only on timeouts, network errors, 429 and 5xx). |
| **`/speech` takes no text** | It reads the interviewer's last message from the session, so a user cannot use the endpoint to spend TTS credits on arbitrary text. |
| **Other users' interviews return 404, not 403** | It does not reveal which interview IDs exist. |
| **Streaming audio with `fetch` + MediaSource** | Playback starts on the first bytes. `axios` cannot stream a response body in the browser. |
| **`bcrypt` directly instead of passlib** | passlib 1.7.4 fails its own start-up check with bcrypt 5.x. |

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Create an account |
| POST | `/api/auth/login` | Get a JWT access token |
| POST | `/api/interview/start` | Start an interview (multipart: `subject`, optional `job_description`, optional `resume` PDF) |
| POST | `/api/interview/submit-answer-audio` | Submit a recording (multipart: `session_id`, `audio`) |
| POST | `/api/interview/submit-answer` | Submit a typed answer (JSON) |
| GET | `/api/interview/{id}/speech` | Stream the interviewer's latest message as MP3 |
| POST | `/api/interview/get-feedback` | Generate (or return stored) feedback |
| GET | `/api/interview/history` | List your interviews |
| GET | `/api/interview/{id}` | One interview with transcript, scores and feedback |
| GET | `/health` | Liveness check |

All `/api/interview/*` routes require `Authorization: Bearer <token>`. Errors share one shape: `{"detail": {"error": "<code>", "message": "<text>"}}`.

## Project structure

```
ai-interview-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py          # app, lifespan (Redis, DB, Gemini, checkpointer), CORS
│   │   ├── api/             # auth.py, interview.py (routes)
│   │   ├── core/            # config, db, security, errors, retry, limiter, logging, redis_client
│   │   ├── models/          # SQLAlchemy: User, InterviewSession, Turn, Feedback
│   │   ├── schemas/         # Pydantic request/response models
│   │   └── services/        # agent (LangGraph), session (Redis), records (Postgres),
│   │                        # scoring, resume, stt (AssemblyAI), tts (Murf)
│   ├── alembic/             # database migrations
│   ├── tests/               # pytest suite
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/           # Landing, Setup, Interview, Results, History
│   │   ├── components/      # Waveform, ScoresChart, ScoreRing, AppShell, Alert, ...
│   │   ├── context/         # AuthContext
│   │   ├── hooks/           # useRecorder (MediaRecorder + Web Audio)
│   │   ├── api/             # axios client, endpoints, streaming speech playback
│   │   └── styles/          # theme.css (design tokens), primitives.css, app.css
│   └── Dockerfile           # Node build stage → nginx
└── docker-compose.yml       # backend + frontend containers
```

## Local setup

**Prerequisites:** Python 3.13, Node 22, a PostgreSQL database, and a Redis with the **RedisJSON and RediSearch** modules (Redis Cloud, Redis Stack, or Redis 8+). The LangGraph Redis checkpointer will not work without them.

**Backend**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then fill in the values (see below)
alembic upgrade head              # create the tables
uvicorn app.main:app --reload --port 8000
```

**Frontend**

```bash
cd frontend
npm install
cp .env.example .env              # set VITE_API_BASE_URL=http://localhost:8000
npm run dev                       # http://localhost:5173
```

**With Docker** (backend and frontend only; PostgreSQL and Redis are external services)

```bash
docker compose --env-file frontend/.env up --build
```

## Environment variables

Names and example shapes only. Never commit real values; both `.env` files are git-ignored and docker-ignored.

**`backend/.env`**

| Variable | Purpose | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL, async driver | `postgresql+asyncpg://user:password@host:5432/dbname` |
| `REDIS_URL` | Redis with JSON + Search modules | `redis://default:password@host:port` |
| `GOOGLE_API_KEY` | Gemini | *(from Google AI Studio)* |
| `GEMINI_MODEL` | Model name (has a default) | `gemini-3.6-flash` |
| `ASSEMBLYAI_API_KEY` | Speech-to-text | *(from AssemblyAI)* |
| `MURF_API_KEY` | Text-to-speech | *(from Murf)* |
| `JWT_SECRET` | Signs access tokens, at least 32 characters | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `JWT_EXPIRE_MINUTES` | Token lifetime | `60` |
| `SUBMIT_ANSWER_RATE_LIMIT` | Per-user limit on answer/speech routes | `10/minute` |
| `CORS_ORIGINS` | Comma-separated frontend origins | `http://localhost:5173` |

The container also reads `PORT` (set by the host; defaults to `8000`).

**`frontend/.env`**

| Variable | Purpose | Example |
|---|---|---|
| `VITE_API_BASE_URL` | Backend base URL, baked into the bundle **at build time** | `http://localhost:8000` |

## Deployment

```
   Vercel                       Render                        Managed services
┌──────────────┐  HTTPS   ┌─────────────────────┐   ┌─ Neon ............ PostgreSQL
│ React build  │ ───────► │ Docker container    │ ──┼─ Redis Cloud ...... Redis (JSON + Search)
│ (static)     │          │ uvicorn on $PORT    │   ├─ Gemini ........... LLM
└──────────────┘          └─────────────────────┘   ├─ AssemblyAI ....... speech-to-text
                                                    └─ Murf ............. text-to-speech
```

- **Frontend (Vercel):** built from source with `npm run build`. `VITE_API_BASE_URL` must be set as a build-time environment variable pointing at the backend.
- **Backend (Render):** runs the backend Docker image. Render provides `$PORT`; all secrets are set as environment variables in the platform, never in the image.
- **CORS:** `CORS_ORIGINS` must contain the deployed frontend origin.
- **Database:** the container does not run migrations. Run `alembic upgrade head` against the production database when the schema changes.
- **Neon and asyncpg:** use the `postgresql+asyncpg://` prefix, and `ssl=require` instead of `sslmode=require` (asyncpg does not accept `sslmode`).

The Docker images: the backend is `python:3.13-slim` running as a non-root user with a health check on `/health`. The frontend is a multi-stage build (Node builds the app, an unprivileged nginx serves it with a single-page-app fallback).

## Testing

```bash
cd backend
pytest
```

- **155 test cases** in 11 modules cover authentication, session isolation (concurrent interviews), interview history, scoring and aggregation, resume parsing, the audio and speech routes, retry and failure behaviour, CORS and rate limiting.
- Tests run against a real Redis and PostgreSQL. Gemini is replaced by stubs, and AssemblyAI and Murf are simulated at the HTTP level, so the real service code runs but no paid API is called.
- Test users and interviews are deleted after each test.
- There is no frontend test suite and no CI pipeline in this repository yet.

## Known limitations and future improvements

Honest notes, not promises:

- **Free-tier limits.** One interview makes about 12 Gemini calls (1 to start, 5 replies, 5 scores, 1 feedback; one more when a resume or job description is used). Free-tier Gemini quotas are easy to hit.
- **Rate limiter is per process** (in-memory). With several backend instances each would count separately. *Future improvement:* a shared limiter store.
- **A failed Gemini turn can duplicate an answer.** LangGraph saves the user's input before the model runs, so re-sending after a failure adds the answer to the conversation twice. *Future improvement:* roll the thread back on failure.
- **No locking on a single interview.** Two simultaneous submits for the same interview are not serialised. *Future improvement:* a per-session lock.
- **Auth is access-token only.** No refresh tokens, no server-side logout, no rate limit on login.
- **Scanned (image-only) PDFs are not supported.** Only PDFs with selectable text.
- **Redis state expires after 2 hours.** An interview can still be read from PostgreSQL afterwards, but it cannot be continued and feedback cannot be generated for it.
