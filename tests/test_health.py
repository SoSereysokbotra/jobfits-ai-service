"""Health endpoint test (Phase 0). Ollama is mocked, but /health also tolerates it being down."""

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@respx.mock
def test_health_ok_with_models():
    respx.get("http://localhost:11434/api/tags").mock(
        return_value=httpx.Response(
            200, json={"models": [{"name": "qwen3"}, {"name": "bge-m3"}]}
        )
    )
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["modelsLoaded"] == ["qwen3", "bge-m3"]


@respx.mock
def test_health_ok_when_ollama_down():
    respx.get("http://localhost:11434/api/tags").mock(
        side_effect=httpx.ConnectError("refused")
    )
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["modelsLoaded"] == []
