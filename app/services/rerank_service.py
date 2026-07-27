"""Rerank logic — quick LLM (listwise) reranker.

One JSON-mode chat call scores the whole shortlist, so it's cheap enough to run
offline. Every requested document id is guaranteed a score in the response
(missing ones default to 0.0), so callers can rely on complete output.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from app.config import Settings
from app.core.errors import AiServiceError, ErrorCode
from app.core.json_repair import extract_json
from app.core.prompts import load_prompt
from app.schemas.rerank import RerankRequest, RerankResponse, RerankScore
from app.services.ollama_client import OllamaClient


class RerankService:
    def __init__(self, ollama: OllamaClient, settings: Settings) -> None:
        self._ollama = ollama
        self._settings = settings

    async def rerank(self, req: RerankRequest) -> RerankResponse:
        payload = json.dumps(
            {
                "candidate": req.query,
                "jobs": [{"id": d.id, "text": d.text} for d in req.documents],
            }
        )
        messages = [
            {"role": "system", "content": load_prompt("rerank.txt")},
            {"role": "user", "content": payload},
        ]
        content = await self._ollama.chat(messages, json_mode=True)
        data = extract_json(content)
        # A model may return a bare list of scores instead of the wrapper object.
        if isinstance(data, list):
            data = {"scores": data}

        try:
            parsed = RerankResponse.model_validate(data)
        except ValidationError as exc:
            raise AiServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                f"Rerank output failed validation: {exc.errors()}",
                502,
            ) from exc

        # Guarantee one score per requested id (clamp to 0-1; default missing to 0).
        by_id = {s.id: s.score for s in parsed.scores}
        return RerankResponse(
            scores=[
                RerankScore(id=d.id, score=_clamp(by_id.get(d.id, 0.0)))
                for d in req.documents
            ]
        )


def _clamp(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0
