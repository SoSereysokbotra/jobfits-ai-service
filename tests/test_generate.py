"""/generate/cover-letter + /generate/interview tests with respx-mocked Ollama (Phase 4)."""

import json

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = {"X-AI-Service-Key": "change-me"}


def _chat(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": content}})


@respx.mock
def test_cover_letter_returns_text():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=_chat("Dear Hiring Manager,\n\nI am excited...\n\nSincerely, Jane")
    )
    r = client.post(
        "/api/v1/generate/cover-letter",
        json={
            "resumeSummary": "Backend developer with 3 years experience",
            "jobTitle": "Backend Engineer",
            "companyName": "Acme",
            "jobDescription": "Build APIs",
            "tone": "professional",
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    assert "Dear Hiring Manager" in r.json()["coverLetter"]


@respx.mock
def test_cover_letter_empty_output_errors():
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat("   "))
    r = client.post(
        "/api/v1/generate/cover-letter",
        json={
            "resumeSummary": "x",
            "jobTitle": "x",
            "companyName": "x",
            "jobDescription": "x",
        },
        headers=AUTH,
    )
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "INVALID_MODEL_OUTPUT"


@respx.mock
def test_interview_questions():
    content = json.dumps(
        {
            "questions": [
                {
                    "question": "Tell me about a hard bug you fixed.",
                    "category": "behavioral",
                    "guidance": "Use the STAR method.",
                }
            ]
        }
    )
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))
    r = client.post(
        "/api/v1/generate/interview",
        json={
            "jobTitle": "Backend Engineer",
            "jobDescription": "Build APIs",
            "level": "SENIOR",
            "kind": "questions",
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["questions"][0]["category"] == "behavioral"
    assert body["feedback"] is None


@respx.mock
def test_interview_questions_bare_list_is_wrapped():
    content = json.dumps(
        [{"question": "Q1", "category": "technical", "guidance": "G1"}]
    )
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))
    r = client.post(
        "/api/v1/generate/interview",
        json={
            "jobTitle": "x",
            "jobDescription": "x",
            "level": "MID",
            "kind": "questions",
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    assert len(r.json()["questions"]) == 1


@respx.mock
def test_interview_feedback():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=_chat("Good structure, but add concrete metrics.")
    )
    r = client.post(
        "/api/v1/generate/interview",
        json={
            "jobTitle": "x",
            "jobDescription": "x",
            "level": "MID",
            "kind": "feedback",
            "answer": "I built a thing",
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    assert "metrics" in r.json()["feedback"]


def test_interview_feedback_requires_answer():
    # No Ollama call expected: the service rejects before reaching the model.
    r = client.post(
        "/api/v1/generate/interview",
        json={
            "jobTitle": "x",
            "jobDescription": "x",
            "level": "MID",
            "kind": "feedback",
        },
        headers=AUTH,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BAD_REQUEST"


def test_interview_rejects_unknown_kind():
    r = client.post(
        "/api/v1/generate/interview",
        json={
            "jobTitle": "x",
            "jobDescription": "x",
            "level": "MID",
            "kind": "chitchat",
        },
        headers=AUTH,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BAD_REQUEST"


def test_generate_requires_api_key():
    r = client.post(
        "/api/v1/generate/cover-letter",
        json={
            "resumeSummary": "x",
            "jobTitle": "x",
            "companyName": "x",
            "jobDescription": "x",
        },
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
