# jobfits-ai-service

The AI microservice for **JobFits**. A stateless **FastAPI** app that the NestJS backend calls
over HTTPS; it turns those requests into calls to **Ollama** (**Qwen 3** for generation,
**BGE-M3** for embeddings) and returns validated JSON.

> **Status:** Planning. No application logic is written yet. See **[BUILD_PLAN.md](./BUILD_PLAN.md)**
> for the full blueprint, API contract, and phased roadmap. The `app/` tree currently holds
> placeholder modules (docstrings only) that describe what each file will contain.

## Responsibilities
- Resume parsing (text → structured JSON)
- Resume scoring (ATS + quality)
- Embeddings for semantic job matching (BGE-M3, 1024-dim)
- Cover letter generation
- Interview questions & answer feedback

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
