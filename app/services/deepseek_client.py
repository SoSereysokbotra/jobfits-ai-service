"""Thin async httpx wrapper around DeepSeek's OpenAI-compatible chat API.

The ONLY module that talks to DeepSeek — the same rule `ollama_client.py` follows, for the
same reason: one place to change when the vendor's shape changes, and one place to audit
when asking "what leaves this machine?".

Chat only. There is no `embed` here and there must not be: DeepSeek publishes no embeddings
endpoint, and the backend stores `vector(1024)` from bge-m3.

Every failure is converted to AiServiceError so `FallbackProvider` can catch one exception
type and route around it, and so a caller that has no fallback still gets the service's
standard error envelope instead of a raw httpx traceback.
"""

from __future__ import annotations

import httpx

from app.config import Settings
from app.core.errors import AiServiceError, ErrorCode


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.deepseek_base_url.rstrip("/")

    async def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        """Run a chat completion and return the assistant message content.

        Args:
            messages: OpenAI-style [{role, content}] list — the same shape OllamaClient
                takes, which is why the two are interchangeable behind ChatProvider.
            json_mode: when True, request strict JSON output.
        """
        payload: dict = {
            "model": self._settings.deepseek_model,
            "messages": messages,
            "stream": False,
            # Spend guard. An unbounded output on a malformed prompt is the one way a
            # cheap per-call cost turns into a real one.
            "max_tokens": self._settings.deepseek_max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        data = await self._post("/chat/completions", payload)
        return self._content(data)

    # ── internals ──────────────────────────────────────────────────────────

    @staticmethod
    def _content(data: dict) -> str:
        """Pull `choices[0].message.content` without letting a shape change raise
        IndexError/KeyError — those would escape as an opaque 500 instead of a
        MODEL_ERROR the fallback knows how to handle."""
        try:
            choices = data["choices"]
            if not choices:
                raise KeyError("choices")
            choice = choices[0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AiServiceError(
                ErrorCode.MODEL_ERROR, "Unexpected DeepSeek chat response shape", 502
            ) from exc
        if not isinstance(content, str):
            raise AiServiceError(
                ErrorCode.MODEL_ERROR, "DeepSeek returned non-text content", 502
            )

        # A completion cut off at max_tokens is a FAILED call, not a short one — for a
        # JSON task the text is a truncated object that cannot parse.
        #
        # MEASURED, 2026-08-20 — why this is raised rather than returned. Truncation
        # arrives as HTTP 200, so without this the bad text flowed back to the caller,
        # blew up in extract_json well outside the provider, and FallbackProvider never
        # saw an exception to route around. A live interview request 502'd while a working
        # local Ollama sat unused. Raising here puts the failure back inside the fallback
        # boundary, where a truncated hosted reply degrades to the local model.
        if choice.get("finish_reason") == "length":
            raise AiServiceError(
                ErrorCode.MODEL_ERROR,
                "DeepSeek output truncated at max_tokens "
                f"({data.get('usage', {}).get('completion_tokens')} completion tokens)",
                502,
            )
        return content

    async def _post(self, path: str, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self._settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        timeout = self._settings.request_timeout_deepseek
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=timeout, headers=headers
            ) as client:
                response = await client.post(path, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise AiServiceError(
                ErrorCode.MODEL_TIMEOUT, f"DeepSeek timed out on {path}", 504
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            # 402 is the expected steady state of a prepaid account, not a bug. Naming it
            # keeps "you ran out of credit" out of the pile of anonymous 4xx.
            detail = (
                "DeepSeek balance exhausted (402)"
                if status == 402
                else f"DeepSeek returned {status} on {path}"
            )
            raise AiServiceError(ErrorCode.MODEL_ERROR, detail, 502) from exc
        except httpx.HTTPError as exc:
            raise AiServiceError(
                ErrorCode.MODEL_ERROR, f"Cannot reach DeepSeek at {path}", 502
            ) from exc
        except ValueError as exc:  # .json() on a non-JSON body
            raise AiServiceError(
                ErrorCode.MODEL_ERROR, "DeepSeek returned a non-JSON body", 502
            ) from exc
