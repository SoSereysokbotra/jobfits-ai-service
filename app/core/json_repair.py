"""
Best-effort "extract valid JSON from an LLM response" helper.

WILL CONTAIN:
- `extract_json(text)`: strip code fences / prose, find the outermost {...} or [...],
  json.loads it; raise AiServiceError(INVALID_MODEL_OUTPUT) if unrecoverable.
Used by resume_service / generate_service after ollama.chat(json=True) as a safety net.

NO LOGIC YET — placeholder.
"""
