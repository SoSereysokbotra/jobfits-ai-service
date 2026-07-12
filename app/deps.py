"""
Shared FastAPI dependencies.

WILL CONTAIN:
- `require_api_key(...)`: validates the `X-AI-Service-Key` header against settings
  (401 UNAUTHORIZED on mismatch). Applied to every router except /health.
- `get_ollama_client(...)`: provides a shared OllamaClient instance.

NO LOGIC YET — placeholder. See BUILD_PLAN.md §3 (auth) and §6 Phase 5.
"""
