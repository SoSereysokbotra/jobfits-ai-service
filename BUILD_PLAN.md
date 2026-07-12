# jobfits-ai-service — Build Plan

**Status:** Planning (no logic written yet — this doc is the blueprint)
**Purpose:** The AI microservice for JobFits. A **FastAPI** app that turns HTTP requests from
the NestJS backend into calls to **Ollama** (running **Qwen 3** for text generation and
**BGE-M3** for embeddings), validates the results, and returns clean JSON.
**Companion doc:** `jobfit-backend/docs/JobFits_AI_Integration_Plan.md` — defines how the
backend consumes this service. The API contract below must stay in sync with it.

---

## 0. Golden rules

1. **This service is the only thing that talks to Ollama.** Ollama listens on
   `localhost:11434` and is never exposed to the internet. Only this FastAPI app is public
   (`https://ai.jobfits.com` in prod).
2. **Stateless.** No database. The service takes text/JSON in, returns JSON out. All storage
   (files, parsed data, embeddings) lives in the backend/Postgres.
3. **The backend never sends files.** It extracts resume text itself (pdf-parse/mammoth) and
   sends plain text. This service is GPU/model-focused only.
4. **Validate every model output.** LLMs return malformed JSON sometimes. Every generation
   endpoint parses + validates against a Pydantic schema and retries/repairs on failure.
5. **Fail loud with structured errors.** Non-2xx responses use the error envelope in §4.6 so
   the backend can decide to fall back to its heuristics.

---

## 1. Tech stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python **3.11+** | 3.10 works; 3.11/3.13 preferred. Use a venv. |
| Web framework | **FastAPI** | Async, auto OpenAPI docs at `/docs`. |
| Server | **uvicorn** (+ gunicorn in prod) | `uvicorn app.main:app --reload` in dev. |
| HTTP client → Ollama | **httpx** (async) | Talks to `http://localhost:11434`. |
| Validation | **pydantic v2** | Request/response schemas + model-output validation. |
| Config | **pydantic-settings** | Loads `.env`. |
| LLM runtime | **Ollama** | Serves Qwen 3 + BGE-M3 locally on the GPU box. |
| Generation model | **Qwen 3** | Resume parsing, scoring, cover letters, interview. |
| Embedding model | **BGE-M3** | 1024-dim vectors for semantic matching. |
| Tests | **pytest** + **respx** | respx mocks Ollama so tests need no GPU. |
| Lint/format | **ruff** + **black** | Optional but recommended. |

> **Do not pin logic to a specific Ollama SDK.** Call Ollama's plain HTTP API with httpx —
> it keeps this service portable and easy to mock.

---

## 2. Target folder structure

```
jobfits-ai-service/
├── app/
│   ├── main.py                 # FastAPI app factory, router registration, health
│   ├── config.py               # Settings (env): OLLAMA_URL, model names, API key, timeouts
│   ├── deps.py                 # Shared dependencies (auth key check, ollama client provider)
│   ├── routers/
│   │   ├── resume.py           # POST /resume/parse, /resume/score
│   │   ├── embed.py            # POST /embed
│   │   ├── generate.py         # POST /generate/cover-letter, /generate/interview
│   │   └── health.py           # GET /health
│   ├── schemas/                # pydantic request/response models (one file per domain)
│   │   ├── resume.py
│   │   ├── embed.py
│   │   ├── generate.py
│   │   └── common.py           # error envelope, shared types
│   ├── services/
│   │   ├── ollama_client.py    # thin httpx wrapper: chat() + embeddings()
│   │   ├── resume_service.py   # build prompt → call ollama → validate → shape response
│   │   ├── embed_service.py
│   │   └── generate_service.py
│   ├── prompts/                # prompt templates (text/jinja) — versioned, easy to tweak
│   │   ├── resume_parse.txt
│   │   ├── resume_score.txt
│   │   ├── cover_letter.txt
│   │   └── interview.txt
│   └── core/
│       ├── errors.py           # AiServiceError, exception handlers → error envelope
│       └── json_repair.py      # best-effort "extract JSON from LLM output" helper
├── tests/
│   ├── test_health.py
│   ├── test_resume.py          # respx-mocked ollama
│   ├── test_embed.py
│   └── test_generate.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── BUILD_PLAN.md               # this file
```

---

## 3. Config (env vars)

```
# .env
OLLAMA_URL=http://localhost:11434
GENERATION_MODEL=qwen3
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024                 # confirm from BGE-M3 model card before backend migration
AI_SERVICE_KEY=<shared secret>     # must match backend AI_SERVICE_KEY
REQUEST_TIMEOUT_GENERATE=60        # seconds
REQUEST_TIMEOUT_EMBED=10
PORT=8000
ENV=development
```

**Auth:** every request (except `/health`) must carry `X-AI-Service-Key: <AI_SERVICE_KEY>`.
Reject with `401` if missing/wrong. This is service-to-service auth, not end-user auth.

---

## 4. API contract (v1)

Base path: `/api/v1`. JSON in/out. Must match the backend's `AiClient`.

### 4.1 `POST /resume/parse`
```jsonc
// request
{ "text": "<raw resume text>", "fileType": "PDF" | "DOCX" }
// response 200
{
  "fullName": "Jane Doe", "email": "jane@x.com", "phone": "+855...",
  "location": "Phnom Penh, KH", "summary": "…",
  "skills": ["TypeScript", "NestJS", "PostgreSQL"],
  "experiences": [
    { "company": "Acme", "title": "Backend Dev",
      "startDate": "2022-01", "endDate": null, "highlights": ["…"] }
  ],
  "educations": [
    { "institution": "RUPP", "degree": "BSc CS",
      "fieldOfStudy": "Computer Science", "graduationYear": 2024 }
  ]
}
```

### 4.2 `POST /resume/score`
```jsonc
// request
{ "text": "<raw resume text>", "targetRole": "Backend Engineer" }  // targetRole optional
// response 200
{ "atsScore": 82, "qualityScore": 76,
  "breakdown": { "formatting": 80, "keywords": 74, "completeness": 90 },
  "suggestions": ["Add measurable outcomes to your Acme role"] }
```

### 4.3 `POST /embed`
```jsonc
// request
{ "inputs": ["senior typescript engineer", "react, node, aws"] }
// response 200
{ "model": "bge-m3", "dim": 1024, "embeddings": [[0.01, ...], [0.02, ...]] }
```

### 4.4 `POST /generate/cover-letter`
```jsonc
// request
{ "resumeSummary": "…", "jobTitle": "…", "companyName": "…",
  "jobDescription": "…", "tone": "professional" }
// response 200
{ "coverLetter": "Dear Hiring Manager, …" }
```

### 4.5 `POST /generate/interview`
```jsonc
// request
{ "jobTitle": "…", "jobDescription": "…", "level": "SENIOR",
  "kind": "questions" | "feedback", "answer": "…" }  // answer only when kind=feedback
// response 200 (kind=questions)
{ "questions": [ { "question": "…", "category": "behavioral", "guidance": "…" } ] }
```

### 4.6 Cross-cutting
- `GET /api/v1/health` → `{ "status": "ok", "modelsLoaded": ["qwen3", "bge-m3"] }`
  (no auth; used by backend health check + load balancers).
- **Error envelope** (any non-2xx):
  ```json
  { "error": { "code": "MODEL_TIMEOUT", "message": "Ollama did not respond in 60s" } }
  ```
  Codes: `UNAUTHORIZED`, `BAD_REQUEST`, `MODEL_TIMEOUT`, `MODEL_ERROR`,
  `INVALID_MODEL_OUTPUT`, `INTERNAL`.

---

## 5. How Ollama is called (reference, not code)

- **Generation** → `POST {OLLAMA_URL}/api/chat` with `{ model: GENERATION_MODEL, messages,
  format: "json", stream: false }`. Using `format: "json"` forces valid JSON for the parse/
  score/interview endpoints.
- **Embeddings** → `POST {OLLAMA_URL}/api/embeddings` (or `/api/embed`) with
  `{ model: EMBEDDING_MODEL, prompt: <text> }`, once per input (or batch if supported).
- Wrap both in `ollama_client.py` behind two methods: `chat(messages, json=True)` and
  `embed(texts)`. Everything else builds prompts and validates results.

---

## 6. Build phases (order of work — no logic yet, this is the roadmap)

Each phase ends with a runnable, tested slice.

### Phase 0 — Skeleton & health (½ day)
- `venv` + `pip install -r requirements.txt`.
- `app/main.py` factory, `config.py`, `GET /health` returning `status: ok`.
- `.env` wired; `uvicorn app.main:app --reload` boots; `/docs` renders.
- Test: `test_health.py`.
- **Backend unblocked:** its Phase 0 `AiClient` can hit `/health`.

### Phase 1 — Ollama client + `/embed` (1 day)
- `ollama_client.py` (`chat`, `embed`) with httpx + timeouts.
- `POST /embed` end-to-end (real BGE-M3).
- Confirm and lock `EMBEDDING_DIM` (feed it back to the backend for the pgvector migration).
- Tests with respx mocking Ollama.

### Phase 2 — `/resume/parse` (1–2 days)
- `prompts/resume_parse.txt` + `resume_service.parse()`.
- Qwen with `format: "json"`, validate against `schemas/resume.py`, `json_repair` fallback.
- Manual test with 2–3 real resumes; compare vs. backend's regex output.

### Phase 3 — `/resume/score` (1 day)
- Prompt + schema + validation. Gate `suggestions` richness on `targetRole` presence.

### Phase 4 — generation: cover letter + interview (1–2 days)
- Prompt templates, schemas, validation, tone handling.
- Interview supports both `questions` and `feedback` kinds.

### Phase 5 — hardening (1 day)
- Auth key dependency on all routers, error handlers → envelope, request logging + latency,
  timeouts verified, retry-on-5xx for embeddings.

### Phase 6 — deploy (RunPod GPU) (1 day)
- Ollama installed on the box, models pulled (`ollama pull qwen3`, `ollama pull bge-m3`).
- gunicorn+uvicorn workers, `.env` set, only FastAPI port exposed, Ollama stays on localhost.
- `/health` reachable at `https://ai.jobfits.com/api/v1/health`.

---

## 7. Local dev quickstart (for when you start building)

```bash
cd D:/Year2/Jobfit/jobfits-ai-service
py -3.11 -m venv .venv           # or python -m venv .venv
.venv\Scripts\activate           # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env           # then edit values

# in a separate terminal, have Ollama running with models pulled:
#   ollama pull qwen3
#   ollama pull bge-m3

uvicorn app.main:app --reload --port 8000
# open http://localhost:8000/docs
```

---

## 8. Open questions (confirm before/while building)

1. **BGE-M3 dimension** — plan assumes **1024**. Verify from the model card in Phase 1; the
   backend's pgvector column depends on this exact number.
2. **Embedding batch support** — does the installed Ollama build embed a list in one call, or
   one-at-a-time? Affects `/embed` throughput for the nightly match batch.
3. **Qwen 3 variant/size** — which quant/size fits the RunPod GPU? Affects latency budgets in
   §3 timeouts.
4. **Prompt language** — resumes may be Khmer/English mixed. Confirm Qwen handles the target
   languages, or add a language hint to prompts.
5. **Contract sign-off** — §4 field names must equal the backend `AiClient`. Lock them before
   both sides code against them.

---

## 9. Definition of done (v1)

- All 6 endpoints in §4 implemented, validated, and tested (mocked Ollama).
- Deployed on RunPod; `/health` green; Ollama private.
- Backend `AiClient` successfully parses a resume + embeds text end-to-end through this service.
- Every endpoint degrades to a structured error (never a 500 with a stack trace) so the
  backend can fall back to heuristics.
```
