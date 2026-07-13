"""Best-effort "extract valid JSON from an LLM response" helper.

Even with Ollama's `format: "json"`, a model can wrap output in prose or code
fences. This recovers the JSON payload or raises INVALID_MODEL_OUTPUT.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.errors import AiServiceError, ErrorCode

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Return the parsed JSON found in `text`, tolerating fences/prose.

    Raises:
        AiServiceError(INVALID_MODEL_OUTPUT): if nothing parseable is found.
    """
    if text is None:
        raise AiServiceError(ErrorCode.INVALID_MODEL_OUTPUT, "Empty model output", 502)

    candidate = text.strip()

    # 1. The whole string is already JSON.
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 2. JSON inside a ```json ... ``` fence.
    fence = _FENCE_RE.search(candidate)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Outermost object or array embedded in surrounding text.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = candidate.find(open_ch)
        end = candidate.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                continue

    raise AiServiceError(
        ErrorCode.INVALID_MODEL_OUTPUT,
        "Model did not return valid JSON",
        502,
    )
