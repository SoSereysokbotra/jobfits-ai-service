"""Prompt template loader. Reads the .txt files in app/prompts/ (cached)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    """Return the contents of app/prompts/<name>. Cached after first read."""
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")
