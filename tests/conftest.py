"""Test isolation from the developer's local `.env`.

FOUND THE HARD WAY, 2026-08-20. `Settings` reads `.env`, so the moment a real
DEEPSEEK_API_KEY was added to a working machine, 12 previously-green tests failed: they
mock Ollama only, but `job_requirements` and `interview` are allowlisted by default, so
those flows tried to reach api.deepseek.com for real.

The suite must not depend on whether the person running it has bought credit. This forces
the hosted provider OFF for every test; the handful that exercise it opt IN by requesting
`deepseek_on`, which overrides these values afterwards.
"""

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Pin the provider-selection env for every test, whatever is in `.env`."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_TASKS", "interview,job_requirements")
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    # get_settings is lru_cached, so a stale instance would outlive the patch.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
