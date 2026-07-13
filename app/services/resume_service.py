"""Resume parsing + scoring logic (BUILD_PLAN.md §6 Phases 2-3).

Flow for each endpoint: build prompt -> Ollama chat (JSON mode) -> repair/parse
JSON -> validate against the response schema. Score values are normalized
(clamped 0-100, rounded) before validation so a slightly out-of-range model does
not fail the whole request.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.core.errors import AiServiceError, ErrorCode
from app.core.json_repair import extract_json
from app.core.prompts import load_prompt
from app.schemas.common import FileType
from app.schemas.resume import ParseResponse, ScoreResponse
from app.services.ollama_client import OllamaClient


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


class ResumeService:
    def __init__(self, ollama: OllamaClient, settings: Settings) -> None:
        self._ollama = ollama
        self._settings = settings

    async def parse(self, text: str, file_type: FileType) -> ParseResponse:
        messages = [
            {"role": "system", "content": load_prompt("resume_parse.txt")},
            {"role": "user", "content": text},
        ]
        content = await self._ollama.chat(messages, json_mode=True)
        data = extract_json(content)
        return self._validate(ParseResponse, data)

    async def score(self, text: str, target_role: str | None) -> ScoreResponse:
        payload = json.dumps({"resume": text, "targetRole": target_role})
        messages = [
            {"role": "system", "content": load_prompt("resume_score.txt")},
            {"role": "user", "content": payload},
        ]
        content = await self._ollama.chat(messages, json_mode=True)
        data = self._normalize_scores(extract_json(content))
        return self._validate(ScoreResponse, data)

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_scores(data: object) -> object:
        """Clamp/round score fields so a lenient model output still validates."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for key in ("atsScore", "ats_score", "qualityScore", "quality_score"):
            value = data.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                data[key] = _clamp_score(value)
        breakdown = data.get("breakdown")
        if isinstance(breakdown, dict):
            data["breakdown"] = {
                k: _clamp_score(v)
                for k, v in breakdown.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            }
        return data

    @staticmethod
    def _validate(model: type[BaseModel], data: object):
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise AiServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                f"Model output failed validation: {exc.errors()}",
                502,
            ) from exc
