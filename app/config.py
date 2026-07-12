"""
Settings loaded from environment (.env) via pydantic-settings.

WILL CONTAIN:
- `Settings` model with: OLLAMA_URL, GENERATION_MODEL, EMBEDDING_MODEL, EMBEDDING_DIM,
  AI_SERVICE_KEY, REQUEST_TIMEOUT_GENERATE, REQUEST_TIMEOUT_EMBED, PORT, ENV.
- A cached `get_settings()` accessor.

See .env.example for the full list. NO LOGIC YET — placeholder.
"""
