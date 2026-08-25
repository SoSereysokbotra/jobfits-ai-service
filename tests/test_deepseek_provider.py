"""DeepSeek provider routing + fallback (docs/DEEPSEEK_PROVIDER_PLAN.md §6).

Two things are under test and only one of them is a feature:

1. DeepSeek is used where it is allowed, and a failure there is invisible to the caller.
2. DeepSeek is NOT used anywhere else — the privacy boundary. Those tests
   (`*_never_leaves_the_machine`) are the reason this file exists. Deleting one silently
   permits a résumé to be shipped to a third party, which no other test would catch.
"""

import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.services.chat_router import ChatRouter
from app.services.ollama_client import OllamaClient

client = TestClient(app)
AUTH = {"X-AI-Service-Key": "change-me"}

OLLAMA_URL = "http://localhost:11434/api/chat"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

QUESTIONS = json.dumps(
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


def _ollama(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": content}})


def _deepseek(content: str) -> httpx.Response:
    """DeepSeek speaks the OpenAI shape — a different envelope to Ollama's, which is
    exactly what DeepSeekClient._content exists to unwrap."""
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _interview() -> httpx.Response:
    return client.post(
        "/api/v1/generate/interview",
        json={
            "jobTitle": "Backend Engineer",
            "jobDescription": "Build APIs",
            "level": "SENIOR",
            "kind": "questions",
        },
        headers=AUTH,
    )


@pytest.fixture
def deepseek_on(isolate_env, monkeypatch):
    """Enable DeepSeek for the default allowlist.

    Sets real env vars rather than patching the router, so `Settings` parsing and
    `ChatRouter._parse_tasks` are exercised too. `get_settings` is lru_cached, so the cache
    has to be cleared on both sides or the setting leaks into or out of the test.

    Takes `isolate_env` explicitly so it is guaranteed to run AFTER the autouse fixture
    that blanks the key — otherwise the ordering decides whether these tests test anything.
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    monkeypatch.setenv("DEEPSEEK_TASKS", "interview,job_requirements")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def deepseek_off(isolate_env, monkeypatch):
    """A blank key must disable the provider even if an allowlist is configured."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_TASKS", "interview,job_requirements")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── it is used where allowed ────────────────────────────────────────────────


@respx.mock
def test_interview_questions_use_deepseek(deepseek_on):
    ds = respx.post(DEEPSEEK_URL).mock(return_value=_deepseek(QUESTIONS))
    ol = respx.post(OLLAMA_URL).mock(return_value=_ollama(QUESTIONS))

    r = _interview()

    assert r.status_code == 200
    assert ds.called
    assert not ol.called, "Ollama must not be called when DeepSeek succeeds"

    sent = json.loads(ds.calls.last.request.content)
    assert sent["model"] == "deepseek-v4-flash"
    # Spend guard: an uncapped output is how a fraction-of-a-cent call becomes a real one.
    assert sent["max_tokens"] == 4096
    # Interview questions are parsed as JSON, so strict JSON mode must be requested.
    assert sent["response_format"] == {"type": "json_object"}


@respx.mock
def test_job_requirements_use_deepseek(deepseek_on):
    content = json.dumps({"requirements": ["Python", "Docker"]})
    ds = respx.post(DEEPSEEK_URL).mock(return_value=_deepseek(content))
    ol = respx.post(OLLAMA_URL).mock(return_value=_ollama(content))

    r = client.post(
        "/api/v1/job/requirements",
        json={"jobTitle": "Backend Engineer", "jobDescription": "Python and Docker"},
        headers=AUTH,
    )

    assert r.status_code == 200
    assert ds.called
    assert not ol.called


# ── failures are invisible to the caller ────────────────────────────────────


@respx.mock
def test_falls_back_to_ollama_on_deepseek_5xx(deepseek_on):
    ds = respx.post(DEEPSEEK_URL).mock(return_value=httpx.Response(500))
    ol = respx.post(OLLAMA_URL).mock(return_value=_ollama(QUESTIONS))

    r = _interview()

    assert r.status_code == 200, "a DeepSeek outage must not surface to the caller"
    assert ds.called and ol.called


@respx.mock
def test_falls_back_to_ollama_when_balance_exhausted(deepseek_on):
    """402 is the expected steady state of a prepaid account, not an exception."""
    ds = respx.post(DEEPSEEK_URL).mock(return_value=httpx.Response(402))
    ol = respx.post(OLLAMA_URL).mock(return_value=_ollama(QUESTIONS))

    r = _interview()

    assert r.status_code == 200
    assert ds.called and ol.called
    assert r.json()["questions"][0]["category"] == "behavioral"


@respx.mock
def test_falls_back_when_deepseek_returns_an_unexpected_shape(deepseek_on):
    """A vendor response shape change must degrade, not raise IndexError into a 500."""
    ds = respx.post(DEEPSEEK_URL).mock(return_value=httpx.Response(200, json={"choices": []}))
    ol = respx.post(OLLAMA_URL).mock(return_value=_ollama(QUESTIONS))

    r = _interview()

    assert r.status_code == 200
    assert ds.called and ol.called


@respx.mock
def test_falls_back_when_deepseek_truncates_at_max_tokens(deepseek_on):
    """FOUND LIVE, 2026-08-20. Truncation arrives as HTTP 200 with a half-written object.

    Before the fix the broken text flowed past the provider and failed in extract_json,
    outside the fallback's reach — so a real request 502'd with a healthy Ollama available.
    """
    truncated = '{"questions": [{"question": "Tell me about a hard bu'
    ds = respx.post(DEEPSEEK_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": truncated}, "finish_reason": "length"}
                ],
                "usage": {"completion_tokens": 4096},
            },
        )
    )
    ol = respx.post(OLLAMA_URL).mock(return_value=_ollama(QUESTIONS))

    r = _interview()

    assert r.status_code == 200, "a truncated hosted reply must degrade, not 502"
    assert ds.called and ol.called
    assert r.json()["questions"][0]["category"] == "behavioral"


@respx.mock
def test_returns_502_when_both_providers_fail(deepseek_on):
    """Adding a provider must not change the both-down behaviour the backend relies on
    to trigger its own template/static fallback."""
    respx.post(DEEPSEEK_URL).mock(return_value=httpx.Response(500))
    respx.post(OLLAMA_URL).mock(return_value=httpx.Response(500))

    r = _interview()

    assert r.status_code == 502
    assert r.json()["error"]["code"] == "MODEL_ERROR"


# ── it is off unless configured ─────────────────────────────────────────────


@respx.mock
def test_blank_key_disables_deepseek_entirely(deepseek_off):
    ds = respx.post(DEEPSEEK_URL).mock(return_value=_deepseek(QUESTIONS))
    ol = respx.post(OLLAMA_URL).mock(return_value=_ollama(QUESTIONS))

    r = _interview()

    assert r.status_code == 200
    assert not ds.called, "a blank key must mean no outbound call at all"
    assert ol.called


# ── the privacy boundary — DO NOT DELETE ────────────────────────────────────


@respx.mock
def test_cover_letter_never_leaves_the_machine(deepseek_on):
    """Carries `resumeSummary`, derived from the user's CV. Not on the allowlist."""
    ds = respx.post(DEEPSEEK_URL).mock(return_value=_deepseek("Dear Hiring Manager,"))
    ol = respx.post(OLLAMA_URL).mock(return_value=_ollama("Dear Hiring Manager,"))

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
    assert not ds.called, "PII BOUNDARY: résumé-derived text must stay local"
    assert ol.called


@respx.mock
def test_resume_parse_never_leaves_the_machine(deepseek_on):
    """The full résumé: name, email, phone, employers. ResumeService is never handed a
    ChatRouter, so this holds regardless of what DEEPSEEK_TASKS says."""
    parsed = json.dumps(
        {
            "fullName": "Jane Doe",
            "email": "jane@x.com",
            "phone": None,
            "location": "Phnom Penh, KH",
            "summary": "Backend developer",
            "skills": ["Python"],
            "experiences": [],
            "educations": [],
        }
    )
    ds = respx.post(DEEPSEEK_URL).mock(return_value=_deepseek(parsed))
    ol = respx.post(OLLAMA_URL).mock(return_value=_ollama(parsed))

    r = client.post(
        "/api/v1/resume/parse",
        json={"text": "Jane Doe, jane@x.com, Backend developer", "fileType": "PDF"},
        headers=AUTH,
    )

    assert r.status_code == 200
    assert not ds.called, "PII BOUNDARY: résumé text must never reach a third party"
    assert ol.called


@respx.mock
def test_interview_feedback_stays_local_by_default(deepseek_on):
    """Feedback carries the user's own written answer, so it is a separate task from
    question generation and is not allowlisted by default."""
    ds = respx.post(DEEPSEEK_URL).mock(return_value=_deepseek("Good structure."))
    ol = respx.post(OLLAMA_URL).mock(return_value=_ollama("Good structure."))

    r = client.post(
        "/api/v1/generate/interview",
        json={
            "jobTitle": "Backend Engineer",
            "jobDescription": "Build APIs",
            "level": "SENIOR",
            "kind": "feedback",
            "answer": "I once debugged a memory leak in production.",
        },
        headers=AUTH,
    )

    assert r.status_code == 200
    assert not ds.called
    assert ol.called


def test_unknown_task_names_cannot_widen_the_allowlist():
    """A typo, or a hopeful entry like `resume_parse`, must fail CLOSED.

    `_parse_tasks` intersects with KNOWN_TASKS, so an unrecognised name is dropped rather
    than trusted — and `resume_parse` is not a known task in the first place, because no
    résumé service is ever handed this router.
    """
    settings = Settings(
        deepseek_api_key="sk-test-key",
        deepseek_tasks="resume_parse,RESUME_SCORE,interview,not_a_task",
    )
    router = ChatRouter(settings, OllamaClient(settings))

    assert router.allows("interview")
    assert not router.allows("resume_parse")
    assert not router.allows("resume_score")
    assert not router.allows("not_a_task")
    assert not router.allows("cover_letter")
