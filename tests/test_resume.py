"""/resume/parse + /resume/score tests with respx-mocked Ollama (Phases 2-3)."""

import json

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = {"X-AI-Service-Key": "change-me"}


def _chat(content: str) -> httpx.Response:
    """Build an Ollama /api/chat response carrying `content` as the message."""
    return httpx.Response(200, json={"message": {"content": content}})


@respx.mock
def test_parse_returns_structured_data():
    content = json.dumps(
        {
            "fullName": "Jane Doe",
            "email": "jane@x.com",
            "phone": None,
            "location": "Phnom Penh, KH",
            "summary": "Backend developer",
            "skills": ["Python", "FastAPI"],
            "experiences": [
                {
                    "company": "Acme",
                    "title": "Backend Dev",
                    "startDate": "2022-01",
                    "endDate": None,
                    "highlights": ["Built the matching service"],
                }
            ],
            "educations": [
                {
                    "institution": "RUPP",
                    "degree": "BSc",
                    "fieldOfStudy": "Computer Science",
                    "graduationYear": 2024,
                }
            ],
        }
    )
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))

    r = client.post(
        "/api/v1/resume/parse",
        json={"text": "…resume text…", "fileType": "PDF"},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fullName"] == "Jane Doe"
    assert body["skills"] == ["Python", "FastAPI"]
    assert body["experiences"][0]["company"] == "Acme"
    assert body["experiences"][0]["endDate"] is None
    assert body["educations"][0]["graduationYear"] == 2024


@respx.mock
def test_parse_repairs_fenced_json():
    content = 'Sure!\n```json\n{"fullName": "John", "skills": []}\n```'
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))

    r = client.post(
        "/api/v1/resume/parse",
        json={"text": "x", "fileType": "DOCX"},
        headers=AUTH,
    )
    assert r.status_code == 200
    assert r.json()["fullName"] == "John"


@respx.mock
def test_parse_invalid_json_raises_envelope():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=_chat("this is not json at all")
    )
    r = client.post(
        "/api/v1/resume/parse",
        json={"text": "x", "fileType": "PDF"},
        headers=AUTH,
    )
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "INVALID_MODEL_OUTPUT"


@respx.mock
def test_score_clamps_and_rounds():
    content = json.dumps(
        {
            "atsScore": 120,  # out of range -> clamp to 100
            "qualityScore": 85.4,  # float -> round to 85
            "breakdown": {"formatting": 90, "keywords": 70.6},
            "suggestions": ["Add measurable outcomes"],
        }
    )
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))

    r = client.post(
        "/api/v1/resume/score",
        json={"text": "x", "targetRole": "Backend Engineer"},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["atsScore"] == 100
    assert body["qualityScore"] == 85
    assert body["breakdown"]["keywords"] == 71
    assert body["suggestions"] == ["Add measurable outcomes"]


def test_parse_requires_api_key():
    r = client.post(
        "/api/v1/resume/parse", json={"text": "x", "fileType": "PDF"}
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_parse_rejects_bad_file_type():
    r = client.post(
        "/api/v1/resume/parse",
        json={"text": "x", "fileType": "TXT"},  # not PDF|DOCX
        headers=AUTH,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BAD_REQUEST"
