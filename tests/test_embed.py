"""/embed test with respx-mocked Ollama (Phase 1)."""

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = {"X-AI-Service-Key": "change-me"}  # matches Settings default


@respx.mock
def test_embed_returns_vectors():
    respx.post("http://localhost:11434/api/embeddings").mock(
        return_value=httpx.Response(200, json={"embedding": [0.1] * 1024})
    )
    r = client.post(
        "/api/v1/embed", json={"inputs": ["hello", "world"]}, headers=AUTH
    )
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "bge-m3"
    assert body["dim"] == 1024
    assert len(body["embeddings"]) == 2
    assert len(body["embeddings"][0]) == 1024


def test_embed_requires_api_key():
    r = client.post("/api/v1/embed", json={"inputs": ["hello"]})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_embed_rejects_empty_inputs():
    r = client.post("/api/v1/embed", json={"inputs": []}, headers=AUTH)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BAD_REQUEST"


@respx.mock
def test_embed_maps_ollama_timeout_to_envelope():
    respx.post("http://localhost:11434/api/embeddings").mock(
        side_effect=httpx.TimeoutException("slow")
    )
    r = client.post("/api/v1/embed", json={"inputs": ["hi"]}, headers=AUTH)
    assert r.status_code == 504
    assert r.json()["error"]["code"] == "MODEL_TIMEOUT"
