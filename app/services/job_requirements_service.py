"""Extract checkable hiring requirements from a job description.

Flow: prompt -> Ollama chat (JSON mode) -> repair/parse JSON -> normalize -> validate,
then score how much of the output is actually grounded in the source text.

The groundedness score is not decoration. Phase C found this model copying a prompt's own
few-shot example into its answer and emitting a placeholder string as evidence; the only
reason those were caught is that something measured the output against the input instead of
trusting it. The same guard applies here — an extractor that quietly starts inventing
requirements would otherwise look identical to one that works.
"""

from __future__ import annotations

import json
import logging
import re

from app.config import Settings
from app.core.errors import AiServiceError, ErrorCode
from app.core.json_repair import extract_json
from app.core.prompts import load_prompt
from app.schemas.job_requirements import (
    JobRequirementsRequest,
    JobRequirementsResponse,
)
from app.services.ollama_client import OllamaClient

logger = logging.getLogger("ai-service")

_WORD_RE = re.compile(r"[a-z0-9+#./]{3,}")
# Words that carry no signal about whether a requirement came from the text.
_STOPWORDS = {
    "and", "the", "for", "with", "you", "our", "are", "will", "have", "has",
    "this", "that", "from", "your", "their", "not", "but", "all", "any", "who",
    "can", "years", "year", "experience", "strong", "using", "use", "work",
    "working", "ability", "knowledge", "skills", "including", "such", "other",
}
_MAX_REQUIREMENTS = 12
# Share of a requirement's meaningful words that must appear in the description for it
# to count as grounded. Below 1.0 because the model is allowed to shorten a sentence.
_GROUNDED_THRESHOLD = 0.6


def _content_words(text: str) -> set[str]:
    """Meaningful lowercase tokens, for comparing a requirement against its source.

    `.` and `/` are inside the token pattern so ".NET" and "CI/CD" survive as single
    tokens — which also means a sentence-ending period gets swallowed ("Kubernetes." !=
    "Kubernetes"), so edge punctuation is stripped afterwards.
    """
    words = set()
    for raw in _WORD_RE.findall(text.lower()):
        word = raw.strip("./")
        if len(word) >= 3 and word not in _STOPWORDS:
            words.add(word)
    return words


class JobRequirementsService:
    def __init__(self, ollama: OllamaClient, settings: Settings) -> None:
        self._ollama = ollama
        self._settings = settings

    async def extract(self, req: JobRequirementsRequest) -> JobRequirementsResponse:
        try:
            prompt = load_prompt(f"job_requirements_{req.prompt_version}.txt")
        except OSError as exc:
            raise AiServiceError(
                ErrorCode.BAD_REQUEST,
                f"Unknown job-requirements prompt version: {req.prompt_version}",
                400,
            ) from exc

        payload = json.dumps(
            {"jobTitle": req.job_title, "jobDescription": req.job_description}
        )
        content = await self._ollama.chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": payload},
            ],
            json_mode=True,
        )

        extracted = self._normalize(extract_json(content))

        # Drop requirements built from words the posting never used, rather than
        # returning them with a warning number attached.
        #
        # Measured on 5 real ingested postings: the model produced "Experience with Docker
        # and Kubernetes" for a WELDING ENGINEER job whose description contains neither
        # word. Shipped unfiltered, that becomes "you're missing Docker" advice to someone
        # applying for a manufacturing role. `groundedness` is still computed over the
        # UNFILTERED output so the number keeps reporting model quality rather than the
        # quality of our filtering.
        grounded = [r for r in extracted if not self._is_invented(r, req.job_description)]

        if len(grounded) < len(extracted):
            logger.warning(
                "job/requirements dropped %d ungrounded of %d",
                len(extracted) - len(grounded),
                len(extracted),
            )

        return JobRequirementsResponse(
            requirements=grounded,
            prompt_version=req.prompt_version,
            groundedness=self._groundedness(extracted, req.job_description),
            dropped_ungrounded=len(extracted) - len(grounded),
        )

    @staticmethod
    def _normalize(data: object) -> list[str]:
        """Coerce the model's output into a clean list of requirement strings.

        A small model is loose with shapes: it may return a bare list, wrap the list in a
        different key, or emit objects instead of strings. Normalising is preferable to
        failing the whole request over a container it chose.
        """
        items: object = data
        if isinstance(data, dict):
            items = data.get("requirements")
            if items is None:
                # Sole list value under some other key.
                lists = [v for v in data.values() if isinstance(v, list)]
                items = lists[0] if len(lists) == 1 else []
        if not isinstance(items, list):
            return []

        out: list[str] = []
        seen: set[str] = set()
        for item in items:
            if isinstance(item, dict):
                # e.g. {"requirement": "..."} or {"text": "..."}
                value = next(
                    (v for v in item.values() if isinstance(v, str) and v.strip()), None
                )
            elif isinstance(item, str):
                value = item
            else:
                value = None
            if not value:
                continue
            cleaned = " ".join(value.split()).strip(" -•*")
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                out.append(cleaned)
        return out[:_MAX_REQUIREMENTS]

    @staticmethod
    def _judge(requirement: str, description: str) -> bool | None:
        """Is this requirement's substance present in the posting? None = cannot tell.

        Lenient on wording (the prompt allows shortening a sentence) and strict on
        substance: a requirement built from words absent from the posting was invented,
        whatever it looks like.

        Returns None when the requirement carries no distinctive words to check — e.g.
        "5 years of experience", which is entirely stopwords. Those are UNJUDGEABLE, not
        invented, and deleting them would silently drop legitimate experience
        requirements. Absence of evidence is not evidence of invention.
        """
        words = _content_words(requirement)
        if not words:
            return None
        overlap = len(words & _content_words(description)) / len(words)
        return overlap >= _GROUNDED_THRESHOLD

    @classmethod
    def _is_invented(cls, requirement: str, description: str) -> bool:
        """Only True when we can judge AND it failed — never on an unjudgeable string."""
        return cls._judge(requirement, description) is False

    @classmethod
    def _groundedness(cls, requirements: list[str], description: str) -> float:
        """Grounded share of the model's raw output, over the items we could judge.

        Unjudgeable items are excluded rather than counted as passes, so a model padding
        its answer with generic filler cannot inflate the score.
        """
        verdicts = [cls._judge(r, description) for r in requirements]
        judgeable = [v for v in verdicts if v is not None]
        if not judgeable:
            return 0.0
        return round(sum(judgeable) / len(judgeable), 3)
