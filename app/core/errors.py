"""
Error types + FastAPI exception handlers.

WILL CONTAIN:
- `AiServiceError(code, message, status)` with codes: UNAUTHORIZED, BAD_REQUEST,
  MODEL_TIMEOUT, MODEL_ERROR, INVALID_MODEL_OUTPUT, INTERNAL.
- Exception handlers that render every error as the §4.6 envelope
  ({ "error": { "code", "message" } }) — never a raw 500 stack trace.

NO LOGIC YET — placeholder.
"""
