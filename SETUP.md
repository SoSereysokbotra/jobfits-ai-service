# jobfits-ai-service — Setup Guide

Exact steps to set up the AI service locally on Windows (PowerShell). There are **two
independent engines**: the **Python/FastAPI service** and the **Ollama inference engine
(+ models)**. You can set up the first without the second.

---

## Part A — Python / FastAPI service (needed to build & run the code)

You do NOT need any AI models for this part. Tests mock Ollama.

```powershell
cd D:\Year2\Jobfit\jobfits-ai-service

# 1. Create a virtual environment.
#    Use a Python you actually have installed — check with:  py -0
#    (this machine has 3.13 and 3.10; 3.13 is recommended)
py -3.13 -m venv .venv          # or:  python -m venv .venv  (uses default Python)

# 2. Activate it (PowerShell)
.\.venv\Scripts\Activate.ps1
#   If blocked by execution policy, run once:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create your local env file
copy .env.example .env
#   then edit .env — at minimum set AI_SERVICE_KEY to any value for now
```

> Once the code is written (Phase 0), you'll run it with:
> `uvicorn app.main:app --reload --port 8000` and open http://localhost:8000/docs
> Right now the modules are placeholders, so this will not serve endpoints yet.

**To deactivate the venv later:** `deactivate`

---

## Part B — Ollama inference engine + models (needed for REAL AI output)

Only needed when you want actual parsing/embeddings/generation (BUILD_PLAN §6 Phase 1+).
Skip this while building against mocks.

### B1. Install Ollama
- Download the Windows installer from **https://ollama.com/download** and run it.
- After install, Ollama runs as a background service on **http://localhost:11434**.
- Verify:
  ```powershell
  ollama --version
  # confirm the server is up:
  curl http://localhost:11434/api/tags
  ```

### B2. Pull the models ("installing the model" = downloading weights, once)
```powershell
# Embedding model — small, safe on a laptop (~1-2 GB)
ollama pull bge-m3

# Generation model — LARGE. Pick a size that fits your machine:
ollama pull qwen3          # full size — needs a strong GPU / lots of RAM
# ...OR a small variant for laptop smoke-testing:
ollama pull qwen3:0.6b     # tiny, for "does it work" tests only
```

### B3. Verify the models respond
```powershell
# list installed models
ollama list

# quick generation test
ollama run qwen3:0.6b "Say hello in JSON"

# quick embeddings test (should return a vector)
curl http://localhost:11434/api/embeddings -Method POST -Body '{"model":"bge-m3","prompt":"hello"}' -ContentType "application/json"
```

### B4. Confirm the embedding dimension (IMPORTANT)
The backend's pgvector column depends on this exact number. Check the length of the vector
returned by the embeddings call above — it should be **1024** for BGE-M3. Record it in `.env`
as `EMBEDDING_DIM` and tell the backend team before the pgvector migration.

---

## ⚠️ Laptop reality check

**Qwen 3 (full) is heavy.** On a laptop without a strong GPU it will be slow or may not fit in
memory. Recommended approaches:

- **Dev locally on mocks** (respx) + `qwen3:0.6b` only for "is JSON flowing?" smoke tests.
- Run the **real** Qwen 3 on the **RunPod GPU server** (prod), and for local testing point
  your `.env` `OLLAMA_URL` at that box instead of localhost:
  ```
  OLLAMA_URL=http://<runpod-host>:11434
  ```
  (Only do this over a trusted/tunnelled connection — Ollama has no auth of its own.)

---

## What you need, by task

| Task | Part A (venv) | Part B (Ollama + models) |
|---|---|---|
| Write FastAPI code | ✅ | ❌ |
| Run `pytest` (mocked Ollama) | ✅ | ❌ |
| Real resume parse / embeddings / cover letter | ✅ | ✅ |
| Deploy to RunPod (prod) | ✅ | ✅ (on the GPU box) |

---

## TL;DR

- **Setting up to build now?** Do **Part A** only. No model download needed.
- **Want real AI output?** Also do **Part B** — install Ollama, then
  `ollama pull bge-m3` and a Qwen 3 variant. That download IS "installing the model."
