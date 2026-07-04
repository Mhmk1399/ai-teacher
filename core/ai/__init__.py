"""AI provider abstraction (ADR-006).

Domain code depends only on ``LanguageModelProvider``. The default adapter is
local Ollama; tests use ``FakeProvider`` so nothing requires a running model.
"""
from core.ai.provider import (  # noqa: F401
    LanguageModelProvider,
    ProviderResponse,
    ProviderError,
)
from core.ai.fake_provider import FakeProvider  # noqa: F401
