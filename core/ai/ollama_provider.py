"""Ollama-backed provider — the default, local-first adapter.

Wraps the existing ``core.llm.OllamaClient`` so we keep its JSON mode, timeouts,
and health check while exposing the provider-agnostic interface.
"""
from __future__ import annotations

import time

from core.ai.provider import LanguageModelProvider, ProviderError, ProviderResponse
from core.llm import LLMError, OllamaClient, get_client


class OllamaProvider(LanguageModelProvider):
    provider_name = "ollama"

    def __init__(self, client: OllamaClient | None = None):
        self._client = client or get_client()
        self.model_name = self._client.model

    def generate_json(self, system: str, user: str) -> ProviderResponse:
        t0 = time.time()
        try:
            text = self._client.chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user}],
                json_mode=True,
            )
        except LLMError as e:
            raise ProviderError(str(e)) from e
        latency_ms = int((time.time() - t0) * 1000)
        if not text:
            raise ProviderError("Empty response from Ollama")
        return ProviderResponse(raw_text=text, latency_ms=latency_ms)
