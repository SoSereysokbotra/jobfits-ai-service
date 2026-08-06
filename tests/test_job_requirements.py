"""/job/requirements tests with respx-mocked Ollama.

The feature's whole value rests on the output being EXTRACTED rather than written, so the
tests focus on shape-tolerance (a small model is loose with containers) and on the
groundedness score actually falling when the model invents.
"""

import json

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = {"X-AI-Service-Key": "change-me"}

DESCRIPTION = (
    "We are hiring a backend engineer. You will build services in Python and deploy "
    "them with Docker on Kubernetes. Requires 5 years of professional experience. "
    "We offer free lunch and a great team culture."
)


def _chat(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": content}})


def _post(**overrides):
    body = {
        "jobTitle": "Backend Engineer",
        "jobDescription": DESCRIPTION,
        **overrides,
    }
    return client.post("/api/v1/job/requirements", json=body, headers=AUTH)


@respx.mock
def test_extracts_requirements_from_description():
    content = json.dumps(
        {"requirements": ["Python", "Docker", "Kubernetes", "5 years of experience"]}
    )
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))

    r = _post()

    assert r.status_code == 200
    body = r.json()
    assert body["requirements"] == ["Python", "Docker", "Kubernetes", "5 years of experience"]
    assert body["promptVersion"] == "v1"


@respx.mock
def test_groundedness_is_high_when_requirements_come_from_the_text():
    content = json.dumps({"requirements": ["Python", "Docker", "Kubernetes"]})
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))

    assert _post().json()["groundedness"] == 1.0


@respx.mock
def test_invented_requirements_are_dropped_not_returned():
    """The guard that makes this endpoint trustworthy.

    Measured on real ingested postings: the model produced "Experience with Docker and
    Kubernetes" for a WELDING ENGINEER job whose description contains neither word.
    Returned unfiltered, that becomes "you're missing Docker" advice for a manufacturing
    role. None of the three below appear in the description either.
    """
    content = json.dumps(
        {"requirements": ["Rust", "Terraform expertise", "Salesforce administration"]}
    )
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))

    body = _post().json()
    assert body["requirements"] == []
    assert body["droppedUngrounded"] == 3
    # Still reports what the MODEL produced, not what survived filtering.
    assert body["groundedness"] == 0.0


@respx.mock
def test_keeps_grounded_requirements_and_drops_only_the_invented_one():
    content = json.dumps({"requirements": ["Python", "Docker", "Salesforce administration"]})
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))

    body = _post().json()
    assert body["requirements"] == ["Python", "Docker"]
    assert body["droppedUngrounded"] == 1
    assert body["groundedness"] == 0.667


@respx.mock
def test_accepts_a_bare_list_from_a_loose_model():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=_chat(json.dumps(["Python", "Docker"]))
    )

    assert _post().json()["requirements"] == ["Python", "Docker"]


@respx.mock
def test_accepts_objects_instead_of_strings():
    content = json.dumps(
        {"requirements": [{"requirement": "Python"}, {"text": "Docker"}]}
    )
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))

    assert _post().json()["requirements"] == ["Python", "Docker"]


@respx.mock
def test_deduplicates_and_strips_bullet_characters():
    content = json.dumps({"requirements": ["- Python", "• python", "  Docker  "]})
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))

    assert _post().json()["requirements"] == ["Python", "Docker"]


@respx.mock
def test_empty_list_is_a_valid_answer():
    # A posting stating no checkable requirement must yield none, not a padded list.
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=_chat(json.dumps({"requirements": []}))
    )

    body = _post().json()
    assert body["requirements"] == []
    assert body["groundedness"] == 0.0


@respx.mock
def test_caps_the_number_of_requirements():
    # Distinct but unjudgeable strings, so the cap is what is under test rather than
    # the groundedness filter.
    content = json.dumps({"requirements": [f"{i} years of experience" for i in range(30)]})
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))

    assert len(_post().json()["requirements"]) == 12


@respx.mock
def test_keeps_requirements_that_are_too_generic_to_verify():
    """"5 years of experience" is all stopwords — unjudgeable, not invented.

    Dropping it would silently delete legitimate experience requirements.
    """
    content = json.dumps({"requirements": ["5 years of experience"]})
    respx.post("http://localhost:11434/api/chat").mock(return_value=_chat(content))

    body = _post().json()
    assert body["requirements"] == ["5 years of experience"]
    assert body["droppedUngrounded"] == 0


def test_unknown_prompt_version_is_rejected():
    r = _post(promptVersion="v99")

    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BAD_REQUEST"


def test_requires_the_api_key():
    r = client.post(
        "/api/v1/job/requirements",
        json={"jobTitle": "x", "jobDescription": "y"},
    )
    assert r.status_code == 401
