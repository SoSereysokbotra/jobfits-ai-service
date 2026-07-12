"""
Thin async httpx wrapper around Ollama's HTTP API. The ONLY module that talks to Ollama.

WILL CONTAIN (Phase 1):
- `chat(messages, json=False)` -> POST {OLLAMA_URL}/api/chat
  (pass format="json" when json=True to force valid-JSON output).
- `embed(texts)` -> POST {OLLAMA_URL}/api/embeddings, returns list of vectors.
- Per-call timeouts from settings; raises AiServiceError(MODEL_TIMEOUT / MODEL_ERROR).

NO LOGIC YET — placeholder. See BUILD_PLAN.md §5.
"""
