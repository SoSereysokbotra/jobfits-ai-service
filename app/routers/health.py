"""Health + readiness. No auth on either; both must be callable when Ollama is down.

TWO ENDPOINTS, TWO QUESTIONS — and conflating them was a real bug:

    /health   Is this process alive?     Always 200 while FastAPI responds.
    /ready    Can it actually do work?   503 when the models are not usable.

`/health` deliberately reports "ok" with Ollama offline: it answers for the FastAPI
process, and a liveness probe that fails on a dependency outage causes restart loops that
fix nothing. But that made "will AI features work?" unanswerable without making a real
call and waiting for it to time out — so anything polling `/health` to decide showed green
through a total outage (jobfit-backend, docs/AI_DEGRADATION_PLAN.md §1).

`/ready` answers that question, and on failure says WHICH model is missing, because
"AI unavailable" and "run `ollama pull bge-m3`" are very different amounts of work.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.config import get_settings
from app.deps import get_ollama_client

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Liveness + best-effort model list. Never fails on Ollama being offline."""
    models: list[str] = []
    try:
        models = await get_ollama_client().list_models()
    except Exception:
        # Health must stay green for the process itself; Ollama status is advisory.
        # /ready is where that status becomes an answer.
        models = []
    return {"status": "ok", "modelsLoaded": models}


def _is_installed(configured: str, installed: list[str]) -> bool:
    """Is `configured` present in `installed`?

    Ollama reports tagged names (`bge-m3:latest`) while `.env` usually carries a bare one
    (`bge-m3`), so a bare config name matches any tag of that model.

    A TAGGED config name must match EXACTLY. `qwen3:4b` is not satisfied by `qwen3:0.6b`
    — they are different models with very different output, and treating them as
    interchangeable is exactly the local-dev mistake this endpoint exists to catch.
    """
    if ":" in configured:
        return configured in installed
    return any(
        name == configured or name.startswith(f"{configured}:") for name in installed
    )


@router.get("/ready")
async def ready(response: Response) -> dict:
    """Readiness: Ollama reachable AND both configured models installed.

    200 -> {"status": "ready", ...}
    503 -> {"status": "not_ready", "reason": ..., "missing": [...], ...}

    A 503 here is an ANSWER, not a failure — it carries the reason and the missing models.
    The backend's AiClient reads both status codes and deliberately never retries this.
    """
    settings = get_settings()

    try:
        installed = await get_ollama_client().list_models()
    except Exception as exc:
        # The case /health reports as "ok". This is the whole reason /ready exists.
        response.status_code = 503
        return {
            "status": "not_ready",
            "reason": "OLLAMA_UNREACHABLE",
            "detail": f"Cannot reach Ollama at {settings.ollama_url}: {exc}",
            "modelsLoaded": [],
        }

    required = {
        "generation": settings.generation_model,
        "embedding": settings.embedding_model,
    }
    models = {
        role: "ok" if _is_installed(name, installed) else "missing"
        for role, name in required.items()
    }
    missing = [name for role, name in required.items() if models[role] == "missing"]

    if missing:
        response.status_code = 503
        return {
            "status": "not_ready",
            "reason": "MODEL_NOT_INSTALLED",
            "detail": "Install with: "
            + "; ".join(f"ollama pull {m}" for m in missing),
            "missing": missing,
            "models": models,
            "modelsLoaded": installed,
        }

    return {
        "status": "ready",
        "models": models,
        "modelsLoaded": installed,
    }
