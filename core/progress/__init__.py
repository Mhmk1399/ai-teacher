"""Deterministic progress + CEFR projection (ADR-005, ADR-002).

Mastery and CEFR are decided here by deterministic, versioned code — never by an
LLM and never in prompts or UI. Projections are pure functions of valid evidence
plus per-competency thresholds, so they are fully rebuildable.
"""
