"""Deterministic fake provider for tests and offline development.

Configure it with either a fixed list of raw JSON strings (consumed in order)
or a callable that maps (system, user) -> raw JSON string. This lets tests
exercise the whole extraction/progress pipeline without Ollama, including
malformed-output paths.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from core.ai.provider import LanguageModelProvider, ProviderError, ProviderResponse


class FakeProvider(LanguageModelProvider):
    provider_name = "fake"

    def __init__(
        self,
        responses: Optional[list[str]] = None,
        handler: Optional[Callable[[str, str], str]] = None,
        model_name: str = "fake-model",
        raise_error: bool = False,
        latency_ms: int = 1,
    ):
        if responses is None and handler is None and not raise_error:
            raise ValueError("FakeProvider needs `responses`, `handler`, or raise_error=True")
        self._responses = list(responses or [])
        self._handler = handler
        self.model_name = model_name
        self._raise_error = raise_error
        self._latency_ms = latency_ms
        self.calls: list[tuple[str, str]] = []

    def generate_json(self, system: str, user: str) -> ProviderResponse:
        self.calls.append((system, user))
        if self._raise_error:
            raise ProviderError("fake provider configured to fail")
        if self._handler is not None:
            text = self._handler(system, user)
        elif self._responses:
            text = self._responses.pop(0)
        else:
            raise ProviderError("FakeProvider exhausted its scripted responses")
        return ProviderResponse(raw_text=text, latency_ms=self._latency_ms)
