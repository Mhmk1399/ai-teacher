"""Provider interface + return types for structured LLM calls."""
from __future__ import annotations

import abc
from dataclasses import dataclass


class ProviderError(RuntimeError):
    """Raised when a provider fails to produce a usable response."""


@dataclass
class ProviderResponse:
    """Raw result of one structured generation call.

    The provider does NOT parse business JSON; callers validate the text against
    their own Pydantic schema so validation logic stays in one place.
    """
    raw_text: str
    latency_ms: int


class LanguageModelProvider(abc.ABC):
    """A provider that returns a single JSON object as text.

    Implementations: ``OllamaProvider`` (default, local), ``FakeProvider`` (tests).
    """

    #: short identifier persisted on EvaluationRun, e.g. "ollama", "fake".
    provider_name: str = "base"
    #: model identifier persisted on EvaluationRun.
    model_name: str = "unknown"

    @abc.abstractmethod
    def generate_json(self, system: str, user: str) -> ProviderResponse:
        """Return a ProviderResponse whose ``raw_text`` is a JSON object.

        Must raise ``ProviderError`` on transport/empty-response failures.
        """
        raise NotImplementedError
