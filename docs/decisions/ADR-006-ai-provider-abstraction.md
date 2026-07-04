# ADR-006: AI provider abstraction

- Status: Accepted
- Date: 2026-06-23

## Context
The MVP calls Ollama directly from scoring. We must stay local-first yet be able
to add hosted providers, and we must test without a running model.

## Decision
Introduce a `LanguageModelProvider` interface with a structured-JSON method.
Adapters: `OllamaProvider` (default, wraps the existing client) and
`FakeProvider` (scripted responses for tests). Domain code depends only on the
interface. Every call is recorded as an `EvaluationRun` (provider, model, prompt
version, latency, success/error, raw + parsed output).

## Consequences
- Tests never require Ollama; missing Ollama cannot crash unrelated features.
- Hosted providers can be added without touching domain logic, but doing so
  moves data off-device and must be consented to (see SECURITY_AND_PRIVACY).
- Prompt/model versions are persisted for reproducibility (ADR-007).
