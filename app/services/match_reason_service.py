"""Structured match-reasoning (Phase C, plan §7).

Flow: prompt -> Ollama chat (JSON mode) -> repair/parse JSON -> normalize ->
validate. A small model (qwen3:0.6b) is loose with shapes, so we normalize
aggressively (0-100 scores, bare strings instead of objects, missing verdict)
before validation, retry ONCE with a corrective nudge, and only then fall back
to a deterministic keyword-overlap answer.

The fallback never invents evidence: it returns no matched requirements and sets
`degraded=True`, so the faithfulness metric cannot be flattered by a model
outage.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from app.config import Settings
from app.core.errors import AiServiceError, ErrorCode
from app.core.json_repair import extract_json
from app.core.prompts import load_prompt
from app.schemas.match_reason import MatchReasonRequest, MatchReasonResponse
from app.services.ollama_client import OllamaClient

logger = logging.getLogger("ai-service")

_WORD_RE = re.compile(r"[a-z0-9+#.]{3,}")
_STOPWORDS = {
    "and", "the", "for", "with", "you", "our", "are", "will", "have", "has",
    "this", "that", "from", "your", "their", "not", "but", "all", "any",
    "who", "can", "job", "role", "work", "team", "years", "year", "experience",
    "including", "such", "other", "more", "into", "than", "over", "about",
    "must", "should", "would", "able", "using", "use", "new", "well", "also",
}
_MAX_ITEMS = 6


class MatchReasonService:
    def __init__(self, ollama: OllamaClient, settings: Settings) -> None:
        self._ollama = ollama
        self._settings = settings

    async def reason(self, req: MatchReasonRequest) -> MatchReasonResponse:
        try:
            prompt = load_prompt(f"match_reason_{req.prompt_version}.txt")
        except OSError as exc:
            raise AiServiceError(
                ErrorCode.BAD_REQUEST,
                f"Unknown prompt version '{req.prompt_version}'",
                400,
            ) from exc
        payload = _build_payload(req)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": payload},
        ]

        parsed = await self._attempt(messages)
        if parsed is None:
            # Retry once with the schema restated — most failures are shape drift.
            retry = messages + [
                {
                    "role": "user",
                    "content": (
                        "Your previous answer was not valid. Reply with ONLY the JSON "
                        'object: {"fitScore": <0.0-1.0>, "matchedRequirements": '
                        '[{"requirement": "...", "evidenceFromCv": "<verbatim cv quote>"}], '
                        '"gaps": [{"requirement": "...", "note": "..."}], '
                        '"verdict": "strong|possible|weak"}'
                    ),
                }
            ]
            parsed = await self._attempt(retry)

        if parsed is None:
            logger.warning("match_reason: falling back to deterministic overlap")
            return self._fallback(req)

        parsed.prompt_version = req.prompt_version
        return parsed

    # ── internals ────────────────────────────────────────────────────────────

    async def _attempt(self, messages: list[dict]) -> MatchReasonResponse | None:
        """One model call. Returns None on any recoverable output problem."""
        try:
            content = await self._ollama.chat(messages, json_mode=True)
            data = _normalize(extract_json(content))
            return MatchReasonResponse.model_validate(data)
        except (AiServiceError, ValidationError) as exc:
            logger.info("match_reason attempt failed: %s", exc)
            return None

    def _fallback(self, req: MatchReasonRequest) -> MatchReasonResponse:
        """Deterministic keyword overlap — no evidence claimed, flagged degraded."""
        cv = _keywords(req.candidate_summary)
        jd = _keywords(f"{req.job_title} {req.job_description}")
        score = round(len(cv & jd) / len(jd), 3) if jd else 0.0
        return MatchReasonResponse(
            fit_score=min(1.0, score),
            matched_requirements=[],
            gaps=[],
            verdict=_verdict_for(score),
            prompt_version=req.prompt_version,
            degraded=True,
        )


def _build_payload(req: MatchReasonRequest) -> str:
    """Format the two input documents for the user message.

    Part of the prompt, so it is versioned with it. v1 sent a JSON blob and the
    eval showed the model lifting job-posting text into `evidenceFromCv`; v2
    delimits the two documents explicitly to make confusing them harder.
    """
    if req.prompt_version == "v1":
        return json.dumps(
            {
                "candidate": req.candidate_summary,
                "job": {"title": req.job_title, "description": req.job_description},
            }
        )
    return (
        "=== CANDIDATE CV (the ONLY source for evidenceFromCv) ===\n"
        f"{req.candidate_summary}\n"
        "=== END CANDIDATE CV ===\n\n"
        "=== JOB POSTING (the ONLY source for requirement) ===\n"
        f"Title: {req.job_title}\n"
        f"{req.job_description}\n"
        "=== END JOB POSTING ==="
    )


def _keywords(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _verdict_for(score: float) -> str:
    if score >= 0.66:
        return "strong"
    return "possible" if score >= 0.33 else "weak"


def _normalize(data: object) -> object:
    """Coerce common small-model deviations into the response schema shape."""
    if not isinstance(data, dict):
        return data
    out = {_camel_key(k): v for k, v in data.items()}

    out["fitScore"] = _score(out.get("fitScore"))
    out["matchedRequirements"] = _pairs(
        out.get("matchedRequirements"), "requirement", "evidenceFromCv"
    )
    out["gaps"] = _pairs(out.get("gaps"), "requirement", "note")

    verdict = out.get("verdict")
    if not isinstance(verdict, str) or verdict.strip().lower() not in (
        "strong",
        "possible",
        "weak",
    ):
        out["verdict"] = _verdict_for(out["fitScore"])
    else:
        out["verdict"] = verdict.strip().lower()
    return out


def _camel_key(key: object) -> object:
    """fit_score -> fitScore (models mix conventions); other keys pass through."""
    if not isinstance(key, str) or "_" not in key:
        return key
    head, *rest = key.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _score(value: object) -> float:
    """Clamp to 0-1, accepting a 0-100 percentage the way small models emit it."""
    if isinstance(value, str):
        try:
            value = float(value.strip().rstrip("%"))
        except ValueError:
            return 0.0
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 0.0
    value = float(value)
    if value > 1.0:
        value = value / 100.0
    return round(max(0.0, min(1.0, value)), 4)


def _pairs(value: object, key_a: str, key_b: str) -> list[dict]:
    """Accept [{a,b}], ["text"], or a single object; drop anything empty."""
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []

    items: list[dict] = []
    for entry in value[:_MAX_ITEMS]:
        if isinstance(entry, str):
            item = {key_a: entry, key_b: ""}
        elif isinstance(entry, dict):
            entry = {_camel_key(k): v for k, v in entry.items()}
            item = {
                key_a: _text(entry.get(key_a)),
                key_b: _text(entry.get(key_b)),
            }
        else:
            continue
        if item[key_a]:
            items.append(item)
    return items


def _text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " ".join(_text(v) for v in value).strip()
    return "" if value is None else str(value)
