"""Thin async httpx wrapper around Ollama's HTTP API.

The ONLY module that talks to Ollama (BUILD_PLAN.md §5). Everything else builds
prompts and validates results. All network failures are converted into
AiServiceError so callers get a structured error, never a raw httpx exception.
"""

from __future__ import annotations

import httpx

from app.config import Settings
from app.core.errors import AiServiceError, ErrorCode


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.ollama_url.rstrip("/")

    async def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        """Run a chat completion and return the assistant message content.

        Args:
            messages: OpenAI-style [{role, content}] list.
            json_mode: when True, ask Ollama for strict JSON output.
        """
        payload: dict = {
            "model": self._settings.generation_model,
            "messages": messages,
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        data = await self._post(
            "/api/chat", payload, timeout=self._settings.request_timeout_generate
        )
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise AiServiceError(
                ErrorCode.MODEL_ERROR, "Unexpected Ollama chat response shape", 502
            ) from exc

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text.

        Ollama's /api/embeddings takes a single prompt, so we issue one request
        per text over a shared connection.
        """
        vectors: list[list[float]] = []
        timeout = self._settings.request_timeout_embed
        async with httpx.AsyncClient(base_url=self._base_url, timeout=timeout) as client:
            for text in texts:
                data = await self._request(
                    client,
                    "/api/embeddings",
                    {"model": self._settings.embedding_model, "prompt": text},
                )
                vector = data.get("embedding")
                if not isinstance(vector, list) or not vector:
                    raise AiServiceError(
                        ErrorCode.MODEL_ERROR, "Ollama returned no embedding", 502
                    )
                vectors.append(vector)
        return vectors

    async def list_models(self) -> list[str]:
        """Return installed model names (best-effort; used by /health)."""
        data = await self._post("/api/tags", None, timeout=5.0, method="GET")
        return [m["name"] for m in data.get("models", []) if "name" in m]

    # ── internals ──────────────────────────────────────────────────────────

    async def _post(
        self,
        path: str,
        payload: dict | None,
        timeout: float,
        method: str = "POST",
    ) -> dict:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=timeout) as client:
            return await self._request(client, path, payload, method=method)

    async def _request(
        self,
        client: httpx.AsyncClient,
        path: str,
        payload: dict | None,
        method: str = "POST",
    ) -> dict:
        try:
            if method == "GET":
                response = await client.get(path)
            else:
                response = await client.post(path, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise AiServiceError(
                ErrorCode.MODEL_TIMEOUT, f"Ollama timed out on {path}", 504
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise AiServiceError(
                ErrorCode.MODEL_ERROR,
                f"Ollama returned {exc.response.status_code} on {path}",
                502,
            ) from exc
        except httpx.HTTPError as exc:
            raise AiServiceError(
                ErrorCode.MODEL_ERROR, f"Cannot reach Ollama at {path}", 502
            ) from exc
