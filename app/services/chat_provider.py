"""The chat abstraction shared by Ollama and DeepSeek (docs/DEEPSEEK_PROVIDER_PLAN.md §3).

`OllamaClient` is deliberately NOT edited to add a second provider — that module documents
itself as "the ONLY module that talks to Ollama" and the invariant is worth keeping. It
already satisfies `ChatProvider` structurally, so it drops in here unchanged.

Only chat generation is abstracted. Embeddings stay welded to Ollama on purpose: DeepSeek
has no embeddings API, and the backend's pgvector column is `vector(1024)` for bge-m3, so a
provider swap there would invalidate every stored embedding rather than degrade politely.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from app.core.errors import AiServiceError

logger = logging.getLogger("ai-service")


@runtime_checkable
class ChatProvider(Protocol):
    """Anything that can run a chat completion and return the message content."""

    async def chat(self, messages: list[dict], json_mode: bool = False) -> str: ...


class FallbackProvider:
    """Try `primary`, fall back to `secondary` on any AiServiceError.

    ANY error falls through, including 4xx. The rule this encodes: adding a hosted provider
    must never make a request MORE likely to fail than it was without one. A 402 (prepaid
    balance exhausted) is the expected steady-state failure and behaves like any other —
    the call quietly lands on the local model.

    The fallback is deliberately not retried or rate-limited. If DeepSeek is down, every
    call pays one failed round-trip before falling back; at this service's volume that is
    cheaper than the state needed to track it, and the timeout bounds the cost.
    """

    def __init__(
        self,
        primary: ChatProvider,
        secondary: ChatProvider,
        *,
        primary_name: str,
        secondary_name: str,
    ) -> None:
        self._primary = primary
        self._secondary = secondary
        self._primary_name = primary_name
        self._secondary_name = secondary_name

    async def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        try:
            return await self._primary.chat(messages, json_mode=json_mode)
        except AiServiceError as exc:
            # Named providers, because "chat failed" in a log cannot tell you whether to
            # top up a balance or restart Ollama.
            logger.warning(
                "%s chat failed (%s: %s); falling back to %s",
                self._primary_name,
                exc.code.value,
                exc.message,
                self._secondary_name,
            )
            return await self._secondary.chat(messages, json_mode=json_mode)
