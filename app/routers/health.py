"""Health router. No auth; safe to call when Ollama is down."""

from __future__ import annotations

from fastapi import APIRouter

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
        models = []
    return {"status": "ok", "modelsLoaded": models}
