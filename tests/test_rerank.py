"""/rerank tests with respx-mocked Ollama (Phase B)."""

import json

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = {"X-AI-Service-Key": "change-me"}


def _chat(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": content}})


REQUEST = {
    "query": "Senior backend engineer, Python, Postgres",
    "documents": [
        {"id": "a", "text": "Senior Backend Engineer - Python/Postgres"},
        {"id": "b", "text": "Graphic Designer"},
        {"id": "c", "text": "Backend Developer - Node"},
    ],
}


@respx.mock
def test_rerank_returns_scores_for_every_document():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=_chat(
            json.dumps({"scores": [{"id": "a", "score": 0.9}, {"id": "b", "score": 0.1}, {"id": "c", "score": 0.6}]})
        )
    )
    r = client.post("/api/v1/rerank", json=REQUEST, headers=AUTH)
    assert r.status_code == 200
    scores = {s["id"]: s["score"] for s in r.json()["scores"]}
    assert scores == {"a": 0.9, "b": 0.1, "c": 0.6}


@respx.mock
def test_rerank_fills_missing_ids_with_zero_and_clamps():
    # Model omits "c" and returns an out-of-range score for "a".
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=_chat(json.dumps({"scores": [{"id": "a", "score": 5}, {"id": "b", "score": -1}]}))
    )
    r = client.post("/api/v1/rerank", json=REQUEST, headers=AUTH)
    assert r.status_code == 200
    scores = {s["id"]: s["score"] for s in r.json()["scores"]}
    assert scores == {"a": 1.0, "b": 0.0, "c": 0.0}  # clamped + missing filled


def test_rerank_requires_api_key():
    r = client.post("/api/v1/rerank", json=REQUEST)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
