"""Chooses a chat provider per task — and is where the privacy boundary lives.

WHY A ROUTER AND NOT A FLAG. "Send generation to DeepSeek" is not one decision, it is one
decision per task, because the tasks do not carry the same data:

    interview          job title + level                      → nothing about the user
    job_requirements   the employer's public posting           → nothing about the user
    interview_feedback the user's own written answer           → user-authored content
    cover_letter       resumeSummary, derived from their CV    → personal data
    resume parse/score the FULL résumé: name, email, phone     → maximum personal data

So the unit of choice is the task, the list is an ALLOWLIST, and anything not named on it
runs locally.

THE BOUNDARY IS STRUCTURAL, NOT A CONVENTION. Services that must never leave the machine —
ResumeService, EmbedService, RerankService, MatchReasonService — keep taking OllamaClient
directly and are never handed a ChatRouter. Adding `resume_parse` to DEEPSEEK_TASKS
therefore does nothing: there is no wire from this router to those services. A privacy rule
that depends on nobody editing the wrong line eventually gets edited.
"""

from __future__ import annotations

from app.config import Settings
from app.services.chat_provider import ChatProvider, FallbackProvider
from app.services.deepseek_client import DeepSeekClient
from app.services.ollama_client import OllamaClient

# Task names usable in DEEPSEEK_TASKS. Anything else in the env var is ignored rather than
# fatal — a typo must fail CLOSED (stay local), never open.
TASK_INTERVIEW = "interview"
TASK_INTERVIEW_FEEDBACK = "interview_feedback"
TASK_JOB_REQUIREMENTS = "job_requirements"
TASK_COVER_LETTER = "cover_letter"

KNOWN_TASKS = frozenset(
    {
        TASK_INTERVIEW,
        TASK_INTERVIEW_FEEDBACK,
        TASK_JOB_REQUIREMENTS,
        TASK_COVER_LETTER,
    }
)


class ChatRouter:
    def __init__(self, settings: Settings, ollama: OllamaClient) -> None:
        self._settings = settings
        self._ollama = ollama
        self._allowed = self._parse_tasks(settings.deepseek_tasks)
        # A blank key is the off switch. Checked here so every caller gets the same
        # answer and no service has to ask "is DeepSeek configured?" itself.
        self._enabled = bool(settings.deepseek_api_key.strip())

    @staticmethod
    def _parse_tasks(raw: str) -> frozenset[str]:
        names = {part.strip().lower() for part in raw.split(",")}
        # Intersect with KNOWN_TASKS so an unrecognised name can never widen the boundary.
        return frozenset(names & KNOWN_TASKS)

    def deepseek_enabled(self) -> bool:
        """Whether a usable key is configured (independent of any task's allowlisting)."""
        return self._enabled

    def allows(self, task: str) -> bool:
        return self._enabled and task in self._allowed

    def for_task(self, task: str) -> ChatProvider:
        """The provider for `task`: DeepSeek-with-Ollama-fallback, or plain Ollama."""
        if not self.allows(task):
            return self._ollama
        return FallbackProvider(
            DeepSeekClient(self._settings),
            self._ollama,
            primary_name="DeepSeek",
            secondary_name="Ollama",
        )
