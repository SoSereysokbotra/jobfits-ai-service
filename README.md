# jobfits-ai-service

The AI microservice for **JobFits**. A stateless **FastAPI** app that the NestJS backend calls
over HTTPS; it turns those requests into calls to **Ollama** (**Qwen 3** for generation,
**BGE-M3** for embeddings) and returns validated JSON.

> **Status:** Implemented and tested. See **[BUILD_PLAN.md](./BUILD_PLAN.md)** for the full
> blueprint, API contract, and phased roadmap.

## Responsibilities
| Endpoint | What it does |
|---|---|
| `POST /embed` | BGE-M3 embeddings (1024-dim) for semantic job matching |
| `POST /resume/parse` | Résumé text → structured JSON |
| `POST /resume/score` | ATS + quality scoring |
| `POST /generate/cover-letter` | Cover letter generation |
| `POST /generate/interview` | Interview questions & answer feedback |
| `POST /rerank` | Listwise LLM reranking of a job shortlist (RAG Phase B) |
| `POST /match/reason` | Structured "why this candidate fits this job" (RAG Phase C) |
| `GET /health` | Liveness + loaded models (no auth) |

### `/match/reason` and prompt versions
Returns `{ fitScore, matchedRequirements[{requirement, evidenceFromCv}], gaps[], verdict,
promptVersion, degraded }`. `evidenceFromCv` is meant to be a **verbatim quote from the CV** —
that is what the backend's faithfulness metric checks, so the prompt forbids paraphrasing.

The optional `promptVersion` field selects `app/prompts/match_reason_<v>.txt` (and its payload
format, see `_build_payload`). Versions are kept, never edited in place, so an old measurement
stays reproducible:
- **v1** — first version; JSON payload. Measured on 150 labeled pairs with qwen3:0.6b:
  **faithfulness 5.9%**, calibration **ρ = 0.137**. The failure was diagnosable from the
  numbers: requirement groundedness was 87.7%, i.e. the model filled *both* fields from the
  job posting, so its "CV evidence" almost never appeared in the CV.
- **v2** — delimits the CV and the job posting explicitly and shows a wrong/right example
  drawn from an unrelated domain (an on-topic example got copied verbatim into
  `evidenceFromCv` as if it were the candidate's own text).

Measured faithfulness/calibration per version lives in `jobfit-backend/eval/reports/`
(`generation-<version>-<timestamp>.md`, plus `BASELINE-GENERATION-2026-08-05.md`) — produced
by the backend's `scripts/eval-generation.ts`.

`degraded: true` means the LLM failed twice and a deterministic keyword-overlap fallback
produced the response — it claims no evidence, and evals must exclude it.

## What it is NOT
- Not a database — it stores nothing. All persistence lives in `jobfit-backend` / Postgres.
- Not public-facing to end users — only the backend calls it (service-to-service key auth).
- Not a file handler — the backend extracts resume text and sends plain text.

## Architecture
```
Frontend → jobfit-backend → jobfits-ai-service (this) → Ollama (localhost:11434)
                                                          ├─ Qwen 3   (generation)
                                                          └─ BGE-M3   (embeddings)
```
Only this service reaches Ollama; Ollama stays private on the GPU box (RunPod).

## Getting started
See [BUILD_PLAN.md §7](./BUILD_PLAN.md) for the dev quickstart. In short: create a venv,
`pip install -r requirements.txt`, copy `.env.example` → `.env`, run Ollama with the models
pulled, then `uvicorn app.main:app --reload`.

## Related docs
- `jobfit-backend/docs/JobFits_AI_Integration_Plan.md` — how the backend consumes this service.
- `jobfit-backend/docs/ARCHITECTURE_ALIGNMENT.md` — overall system conventions.
