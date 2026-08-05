"""/match/reason tests with respx-mocked Ollama (Phase C)."""

import json

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = {"X-AI-Service-Key": "change-me"}
CHAT = "http://localhost:11434/api/chat"

REQUEST = {
    "candidateSummary": "5 years building Python and Postgres APIs at a fintech. Led a team of 3.",
    "jobTitle": "Senior Backend Engineer",
    "jobDescription": "Python, Postgres, 5+ years, Kubernetes experience required.",
}

GOOD = {
    "fitScore": 0.8,
    "matchedRequirements": [
        {"requirement": "Python", "evidenceFromCv": "5 years building Python and Postgres APIs"}
    ],
    "gaps": [{"requirement": "Kubernetes", "note": "Not mentioned in the CV"}],
    "verdict": "strong",
}


def _chat(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": content}})


@respx.mock
def test_returns_structured_reasoning():
    respx.post(CHAT).mock(return_value=_chat(json.dumps(GOOD)))
    r = client.post("/api/v1/match/reason", json=REQUEST, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["fitScore"] == 0.8
    assert body["verdict"] == "strong"
    assert body["matchedRequirements"][0]["evidenceFromCv"].startswith("5 years")
    assert body["gaps"][0]["requirement"] == "Kubernetes"
    assert body["promptVersion"] == "v2"  # current best-measured default
    assert body["degraded"] is False


@respx.mock
def test_normalizes_percentage_score_snake_keys_and_missing_verdict():
    respx.post(CHAT).mock(
        return_value=_chat(
            json.dumps(
                {
                    "fit_score": 85,  # 0-100 instead of 0-1
                    "matched_requirements": [
                        {"requirement": "Python", "evidence_from_cv": "Python and Postgres APIs"}
                    ],
                    "gaps": ["Kubernetes"],  # bare string instead of an object
                    # verdict omitted entirely
                }
            )
        )
    )
    r = client.post("/api/v1/match/reason", json=REQUEST, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["fitScore"] == 0.85
    assert body["verdict"] == "strong"  # derived from the score
    assert body["gaps"] == [{"requirement": "Kubernetes", "note": ""}]
    assert body["degraded"] is False


@respx.mock
def test_retries_once_then_succeeds():
    route = respx.post(CHAT).mock(
        side_effect=[_chat("sorry, I cannot do that"), _chat(json.dumps(GOOD))]
    )
    r = client.post("/api/v1/match/reason", json=REQUEST, headers=AUTH)
    assert r.status_code == 200
    assert route.call_count == 2
    assert r.json()["fitScore"] == 0.8
    assert r.json()["degraded"] is False


@respx.mock
def test_falls_back_deterministically_after_two_failures():
    route = respx.post(CHAT).mock(return_value=_chat("not json at all"))
    r = client.post("/api/v1/match/reason", json=REQUEST, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert route.call_count == 2
    assert body["degraded"] is True
    # The fallback never claims evidence it cannot quote.
    assert body["matchedRequirements"] == []
    assert 0.0 <= body["fitScore"] <= 1.0
    assert body["verdict"] in ("strong", "possible", "weak")


@respx.mock
def test_falls_back_when_ollama_is_unreachable():
    respx.post(CHAT).mock(side_effect=httpx.ConnectError("refused"))
    r = client.post("/api/v1/match/reason", json=REQUEST, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["degraded"] is True


@respx.mock
def test_v1_sends_a_json_payload_and_v2_sends_delimited_documents():
    """The payload format is versioned with the prompt (v2 fixed cv/jd confusion)."""
    seen: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["messages"][-1]["content"])
        return _chat(json.dumps(GOOD))

    respx.post(CHAT).mock(side_effect=capture)

    client.post(
        "/api/v1/match/reason", json={**REQUEST, "promptVersion": "v1"}, headers=AUTH
    )
    assert json.loads(seen[0])["candidate"] == REQUEST["candidateSummary"]

    client.post("/api/v1/match/reason", json=REQUEST, headers=AUTH)  # default = v2
    assert "=== CANDIDATE CV" in seen[1]
    assert "=== JOB POSTING" in seen[1]
    assert REQUEST["candidateSummary"] in seen[1]


@respx.mock
def test_v2_response_reports_its_prompt_version():
    respx.post(CHAT).mock(return_value=_chat(json.dumps(GOOD)))
    r = client.post(
        "/api/v1/match/reason", json={**REQUEST, "promptVersion": "v2"}, headers=AUTH
    )
    assert r.status_code == 200
    assert r.json()["promptVersion"] == "v2"


def test_unknown_prompt_version_is_a_bad_request():
    r = client.post(
        "/api/v1/match/reason",
        json={**REQUEST, "promptVersion": "v999"},
        headers=AUTH,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BAD_REQUEST"


def test_requires_api_key():
    r = client.post("/api/v1/match/reason", json=REQUEST)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
