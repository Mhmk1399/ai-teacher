"""Strict Pydantic schemas for AI competency-extraction I/O.

The competency detector LLM must return JSON matching ``ExtractionResult``. We
validate every field; malformed output raises and is recorded as a failed
``EvaluationRun`` rather than silently corrupting learner progress (ADR-006).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Outcome = Literal[
    "correct", "partially_correct", "incorrect", "not_demonstrated", "uncertain"
]


class ObservationOut(BaseModel):
    """One competency observation as proposed by the LLM."""
    model_config = ConfigDict(extra="forbid")

    competency_code: str = Field(min_length=1, max_length=32)
    outcome: Outcome
    correctness_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_excerpt: Optional[str] = Field(default=None, max_length=2000)
    detected_error: Optional[str] = Field(default=None, max_length=2000)
    explanation: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("competency_code")
    @classmethod
    def _normalize_code(cls, v: str) -> str:
        return v.strip().upper()


class ExtractionResult(BaseModel):
    """Top-level object the LLM must return."""
    model_config = ConfigDict(extra="forbid")

    observations: list[ObservationOut] = Field(default_factory=list)


class CompetencyDefinitionIn(BaseModel):
    """Validation schema for seeding/creating a competency (catalog integrity)."""
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=160)
    domain: str = Field(min_length=1, max_length=32)
    subdomain: Optional[str] = Field(default=None, max_length=64)
    skill: str = Field(default="production", max_length=24)
    description: Optional[str] = None
    cefr_level_hint: Literal["A1", "A2", "B1", "B2", "C1", "C2"]
    performance_descriptors: list[str] = Field(default_factory=list)
    positive_patterns: list[str] = Field(default_factory=list)
    negative_patterns: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    evidence_required: int = Field(default=5, ge=1, le=100)
    accuracy_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    contexts_required: int = Field(default=2, ge=1, le=20)
    prerequisites: list[str] = Field(default_factory=list)
    active: bool = True
    version: int = Field(default=1, ge=1)

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, v: str) -> str:
        return v.strip().upper()
