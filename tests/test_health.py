"""Health endpoint test (Phase 0). Ollama is mocked, but /health also tolerates it being down."""

import httpx
import respx
from fastapi.testclient import TestClient

from app.config import get_settings
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


# ── /ready — the capability signal /health could never give ──────────────────
#
# /health returns 200 with Ollama dead, by design. That made "is the AI usable?"
# unanswerable without making a real call and waiting for it to time out. These pin the
# three states /ready distinguishes.


@respx.mock
def test_ready_when_ollama_up_and_models_installed():
    respx.get("http://localhost:11434/api/tags").mock(
        return_value=httpx.Response(
            200, json={"models": [{"name": "qwen3:latest"}, {"name": "bge-m3:latest"}]}
        )
    )
    r = client.get("/api/v1/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["models"] == {"generation": "ok", "embedding": "ok"}


@respx.mock
def test_ready_503_when_ollama_unreachable():
    respx.get("http://localhost:11434/api/tags").mock(
        side_effect=httpx.ConnectError("refused")
    )
    r = client.get("/api/v1/ready")
    # The case /health reports as "ok" — the whole reason this endpoint exists.
    assert r.status_code == 503
    assert r.json()["reason"] == "OLLAMA_UNREACHABLE"


@respx.mock
def test_ready_503_names_the_model_that_is_missing():
    # Ollama is up, but nobody pulled the embedding model.
    respx.get("http://localhost:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen3:latest"}]})
    )
    r = client.get("/api/v1/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["reason"] == "MODEL_NOT_INSTALLED"
    # Actionable: says WHICH model, so the fix is "ollama pull bge-m3".
    assert body["missing"] == ["bge-m3"]
    assert body["models"] == {"generation": "ok", "embedding": "missing"}


@respx.mock
def test_ready_matches_bare_config_name_against_tagged_install():
    # `.env` says `bge-m3`; `ollama list` says `bge-m3:latest`. Same model.
    respx.get("http://localhost:11434/api/tags").mock(
        return_value=httpx.Response(
            200, json={"models": [{"name": "qwen3:latest"}, {"name": "bge-m3:latest"}]}
        )
    )
    assert client.get("/api/v1/ready").status_code == 200


@respx.mock
def test_ready_does_not_accept_a_different_size_of_the_same_model(monkeypatch):
    # Configured qwen3:4b but only qwen3:0.6b installed — a real local-dev mistake, and
    # exactly what a bare-name match would wave through.
    monkeypatch.setenv("GENERATION_MODEL", "qwen3:4b")
    get_settings.cache_clear()
    respx.get("http://localhost:11434/api/tags").mock(
        return_value=httpx.Response(
            200, json={"models": [{"name": "qwen3:0.6b"}, {"name": "bge-m3:latest"}]}
        )
    )
    r = client.get("/api/v1/ready")
    assert r.status_code == 503
    assert r.json()["missing"] == ["qwen3:4b"]
    get_settings.cache_clear()
