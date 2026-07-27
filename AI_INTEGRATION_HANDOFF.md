# JobFits — AI Integration Handoff (new-chat brief)

> Paste this whole file (or point the assistant at it) to start a fresh chat that
> integrates `jobfits-ai-service` into the NestJS backend. It is self-contained —
> no dependency on any prior conversation.

---

You are working on **JobFits**, a microservice app with three local repos on a
**Windows** machine (use PowerShell or Git Bash):

- **Frontend** (Next.js 15): `D:\Year2\Jobfit\jobfit-frontend` — runs on `http://localhost:3000`
- **Backend** (NestJS + Prisma + Postgres/Supabase + Redis): `D:\Year2\Jobfit\jobfit-backend` — runs on `http://localhost:4000`, global route prefix `/api/v1`
- **AI service** (FastAPI + Ollama): `D:\Year2\Jobfit\jobfits-ai-service` — runs on `http://localhost:8000`, prefix `/api/v1`; it calls Ollama on `http://localhost:11434` (models: `qwen3` for generation, `bge-m3` for 1024-dim embeddings)

**Goal:** Integrate the AI service into the NestJS backend so the platform's AI
features (resume parsing, resume scoring, semantic job matching / recommendations,
cover letters, interview coaching) become real, replacing the current
heuristics/stubs — while keeping heuristic fallbacks so nothing hard-fails when the
GPU/AI box is down.

## READ THESE FIRST (authoritative — the plan is already written; follow it, don't redesign)
1. `jobfit-backend/docs/JobFits_AI_Integration_Plan.md` — the phased backend plan + the AI API contract (§3) + pgvector decision (§4). **Source of truth.**
2. `jobfits-ai-service/BUILD_PLAN.md` — the AI service's API contract (must stay in sync).
3. `jobfits-ai-service/SETUP.md` — how to run the AI service (Part A = FastAPI only, no models; Part B = Ollama + models for real output).
4. `jobfit-backend/docs/ARCHITECTURE_ALIGNMENT.md` and `jobfit-backend/docs/JobFits_Backend_PATTERNS.md` — backend DDD conventions.

## Current state (verified)
- The AI service is **already implemented** (real FastAPI code in `app/routers/*` + `app/services/*`: `/health`, `/embed`, `/resume/parse`, `/resume/score`, `/generate/cover-letter`, `/generate/interview`). Its README says "Planning" but that is **stale**. It needs Ollama+models running for real output; `/health` works without them; auth is header `X-AI-Service-Key`.
- The backend has **no AI client at all** — no `AiModule`, no `AI_SERVICE_KEY`/`AI_SERVICE_URL` in `.env`. This must be built first.
- Backend resume parsing (`src/modules/resume/application/services/resume-parser.service.ts`) and scoring (`resume-scorer.service.ts`) are **heuristics** with a clean seam for an AI call.
- Backend `src/modules/matching/` is **all stubs**: `domain/scoring/{skills,experience,location}-scorer.ts` and `weighted-match.calculator.ts` are 1-line placeholders; `compute-match-score.use-case.ts` is a `TODO`; there is **no matching controller/endpoint**. `MatchScore` model exists (`jobId`, `jobSeekerProfileId`, `score`, `breakdown`, `@@unique([jobId, jobSeekerProfileId])`).
- Frontend recommendations (`src/features/matching/api/matching.api.ts`) return `MOCK_JOBS`.
- Postgres is Supabase (the **pgvector** extension is available there).

## AI API contract (from the plan, §3)
All JSON over `/api/v1`, header `X-AI-Service-Key`; timeouts 60s generate/parse, 10s embed/health.
- `POST /resume/parse` `{ text, fileType }` → structured resume JSON (fullName, email, phone, location, summary, skills[], experiences[], educations[])
- `POST /resume/score` `{ text, targetRole? }` → `{ atsScore, qualityScore, breakdown, suggestions }`
- `POST /embed` `{ inputs: string[] }` → `{ model, dim: 1024, embeddings: number[][] }`
- `POST /generate/cover-letter` `{ resumeSummary, jobTitle, companyName, jobDescription, tone }` → `{ coverLetter }`
- `POST /generate/interview` `{ jobTitle, jobDescription, level, kind: "questions"|"feedback", answer? }` → questions or feedback
- `GET /health` (no auth) → `{ status, modelsLoaded }`
- Errors: `{ error: { code, message } }` with codes `UNAUTHORIZED` / `BAD_REQUEST` / `MODEL_TIMEOUT` / `MODEL_ERROR` / `INVALID_MODEL_OUTPUT` / `INTERNAL`

## Backend conventions & gotchas (important)
- Path aliases: `@common/*`, `@core/*`, `@shared/*`, `@modules/*`, `@infra/*`, `@events/*`, `@config/*`. `PrismaModule` and `EventBusModule` are `@Global`. Auth: global `JwtAuthGuard` + `RolesGuard`; use `@Roles('JOB_SEEKER'|'EMPLOYER'|'ADMIN')`, `@Public()`, `@CurrentUser()` → `{ id, email, role }`.
- After any `schema.prisma` change: run `npx prisma generate` **before** `tsc`. **Gotcha:** on Windows `prisma generate` fails with `EPERM` on the query-engine DLL while the backend dev server is running — stop the dev server first, or note that a restart is required. `prisma migrate dev` is interactive and fails non-interactively when there's a constraint warning — hand-write the migration SQL and run `npx prisma migrate deploy` instead.
- The backend is currently on git branch **`feature/healthcheck`** and has **unrelated uncommitted WIP** (employer/job/seed files that are NOT yours) — do not stage those; commit only files you create/change.
- Verify types with `npx tsc --noEmit -p tsconfig.json`. Node is **v22** (global `fetch` available). `@nestjs/axios` may or may not be installed — check `package.json`.
- Seeded accounts for testing: admin `admin@jobfit.com` / `Admin123!` (run `npx prisma db seed`).

## Your task — do it in the plan's phase order, one shippable slice at a time

### Phase 0 (do this first — foundation, testable WITHOUT Ollama)
Build the `AiModule`:
- `src/config/ai.config.ts` — `AI_SERVICE_URL` (default `http://localhost:8000/api/v1`), `AI_SERVICE_KEY`, `AI_TIMEOUT_MS_GENERATE=60000`, `AI_TIMEOUT_MS_EMBED=10000`. Add these to `.env` and `.env.example` (do NOT commit real secrets).
- `src/infra/ai/ai.client.ts` — typed client with methods `health()`, `parseResume()`, `scoreResume()`, `embed()`, `generateCoverLetter()`, `generateInterview()`, sending `X-AI-Service-Key`, per-call timeout, **1 retry on 5xx/timeout**, throwing a typed `AiServiceError` so callers can fall back to heuristics. (Use `@nestjs/axios` HttpService, or Node global `fetch`.)
- `src/infra/ai/ai.module.ts` — `@Global`, provides/exports `AiClient`. Wire into `app.module.ts`.
- **Verify:** unit-test the client against a mocked HTTP server, and hit the real AI service `/health` (start it via SETUP Part A — no models needed) from a throwaway script. Confirm `tsc` clean.

**Deliverable:** the backend can call the AI service (even if the service returns canned JSON). This unblocks every later phase and lets both repos be built against the same spec.

### Then, in order
- **Phase 1 — Resume parsing via Qwen:** in `resume-parser.service.ts`, swap `extractStructuredData()` for `aiClient.parseResume(text, fileType)`; on `AiServiceError`, fall back to the current regex extractor (mark `parsedBy: "heuristic"`). Keep the BullMQ async flow + `ResumeParsedEvent`.
- **Phase 2 — Resume scoring via AI** (good first *visible* feature): `aiClient.scoreResume()` behind `ResumeScorerService`, heuristic sub-scores as fallback; persist to `Resume.atsScore`/`qualityScore` (already shown in the frontend `/resumes` page). Gate `suggestions` behind subscription tier.
- **Phase 3 — Semantic matching (the big one):** `CREATE EXTENSION vector`; add `vector(1024)` embedding columns to `jobs` and to candidate embeddings (per-profile or per-resume — confirm with user); embed on job-publish / profile-change; implement the stub scorers (cosine similarity for skills, deterministic rules for experience/location/salary); finish `ComputeMatchScoreUseCase` + the recompute batch; add a recommendations endpoint; wire the frontend `matching.api.ts`. **Ask the user before this migration — it changes the DB.**
- **Phase 4 — Generation:** cover-letter + interview endpoints → `aiClient.generate*`, tier-gated.

## Constraints
- Every AI call must degrade gracefully to the existing heuristic (never hard-fail).
- Keep the AI service stateless — the backend does file text extraction and all persistence.
- Confirm with the user whether **Ollama + `bge-m3`/`qwen3` are running** before relying on real output for Phases 1–4; **Phase 0 does not need them**.
- Ask the user before Phase 3's pgvector migration.

**Start by reading the four docs above, confirming the current state, then implement and verify Phase 0. Report before moving to the next phase.**
