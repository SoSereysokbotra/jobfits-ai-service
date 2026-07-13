"""Embedding request/response schemas. Contract: BUILD_PLAN.md §4.3."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class EmbedRequest(CamelModel):
    inputs: list[str] = Field(..., min_length=1)


class EmbedResponse(CamelModel):
    model: str
    dim: int
    embeddings: list[list[float]]
