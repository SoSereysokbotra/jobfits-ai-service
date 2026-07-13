"""Embedding logic (BUILD_PLAN.md §6 Phase 1)."""

from __future__ import annotations

import logging

from app.config import Settings
from app.schemas.embed import EmbedResponse
from app.services.ollama_client import OllamaClient

logger = logging.getLogger("ai-service")


class EmbedService:
    def __init__(self, ollama: OllamaClient, settings: Settings) -> None:
        self._ollama = ollama
        self._settings = settings

    async def embed(self, inputs: list[str]) -> EmbedResponse:
        vectors = await self._ollama.embed(inputs)

        # Report the actual dimension; warn (don't fail) if it disagrees with
        # the configured EMBEDDING_DIM the backend's pgvector column relies on.
        dim = len(vectors[0])
        if dim != self._settings.embedding_dim:
            logger.warning(
                "Embedding dim %d != configured EMBEDDING_DIM %d; "
                "update .env and the backend pgvector column to match.",
                dim,
                self._settings.embedding_dim,
            )

        return EmbedResponse(
            model=self._settings.embedding_model,
            dim=dim,
            embeddings=vectors,
        )
