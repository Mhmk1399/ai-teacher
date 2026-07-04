"""Competency-domain ORM models.

These tables are **additive**: they reference the existing assessment tables
(`students`, `answers`) via foreign keys but never alter them. They share the
same declarative ``Base`` as ``core.models`` so a single metadata drives both
``create_all`` and Alembic autogenerate.

Source of truth = ``CompetencyDefinition`` + ``EvidenceObservation``.
``LearnerCompetency`` and ``CEFRProjection`` are *projections* — pure functions
of valid evidence + thresholds, fully rebuildable (see ADR-001, ADR-002, ADR-005).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models import Base


# ---------------- Catalog (expert-authored truth) ----------------

class CompetencyDefinition(Base):
    """One measurable language competency, e.g. GR-B1-09 First Conditional."""
    __tablename__ = "competency_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    domain: Mapped[str] = mapped_column(String(32), index=True)          # grammar | vocabulary | ...
    subdomain: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    skill: Mapped[str] = mapped_column(String(24), default="production")  # production | reception | ...
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cefr_level_hint: Mapped[str] = mapped_column(String(2), index=True)

    performance_descriptors: Mapped[list] = mapped_column(JSON, default=list)
    positive_patterns: Mapped[list] = mapped_column(JSON, default=list)
    negative_patterns: Mapped[list] = mapped_column(JSON, default=list)
    exceptions: Mapped[list] = mapped_column(JSON, default=list)

    # Mastery rule parameters (consumed by the deterministic progress engine).
    evidence_required: Mapped[int] = mapped_column(Integer, default=5)
    accuracy_threshold: Mapped[float] = mapped_column(Float, default=0.80)
    contexts_required: Mapped[int] = mapped_column(Integer, default=2)

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    prerequisites: Mapped[list["CompetencyPrerequisite"]] = relationship(
        back_populates="competency",
        foreign_keys="CompetencyPrerequisite.competency_id",
        cascade="all, delete-orphan",
    )


class CompetencyPrerequisite(Base):
    """Directed edge: ``competency`` requires/supports ``prerequisite``."""
    __tablename__ = "competency_prerequisites"

    id: Mapped[int] = mapped_column(primary_key=True)
    competency_id: Mapped[int] = mapped_column(
        ForeignKey("competency_definitions.id"), index=True
    )
    prerequisite_competency_id: Mapped[int] = mapped_column(
        ForeignKey("competency_definitions.id"), index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(16), default="requires")
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    competency: Mapped["CompetencyDefinition"] = relationship(
        back_populates="prerequisites", foreign_keys=[competency_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "competency_id", "prerequisite_competency_id", name="uq_competency_prereq"
        ),
    )


# ---------------- Evidence (raw, traceable truth) ----------------

class EvidenceObservation(Base):
    """One observation about one learner and one competency, from one source."""
    __tablename__ = "evidence_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    competency_id: Mapped[int] = mapped_column(
        ForeignKey("competency_definitions.id"), index=True
    )

    source_type: Mapped[str] = mapped_column(String(32), index=True)  # exam_answer | conversation_turn | ...
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    activity_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    context_key: Mapped[str] = mapped_column(String(64), default="default")  # diversity bucket
    modality: Mapped[str] = mapped_column(String(16), default="text")

    observed_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20))  # correct|partially_correct|incorrect|not_demonstrated|uncertain
    correctness_score: Mapped[float] = mapped_column(Float, default=0.0)
    evaluator_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_weight: Mapped[float] = mapped_column(Float, default=1.0)
    detected_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    prompt_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    evaluator_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    evaluation_run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("evaluation_runs.id"), nullable=True, index=True
    )

    # pending | accepted | rejected | overridden
    human_review_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    human_override: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_obs_learner_competency", "learner_id", "competency_id"),
        Index("ix_obs_source", "source_type", "source_id"),
    )


# ---------------- AI evaluation provenance ----------------

class EvaluationRun(Base):
    """Records one AI evaluation operation for reproducibility & debugging."""
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluator_type: Mapped[str] = mapped_column(String(40))  # competency_extractor | scorer | ...
    model_provider: Mapped[str] = mapped_column(String(32))  # ollama | fake | openai
    model_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    input_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    raw_input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parsed_output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------- Projections (derived, rebuildable) ----------------

class LearnerCompetency(Base):
    """Computed per-learner-per-competency state. One row per pair (rebuildable)."""
    __tablename__ = "learner_competencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    competency_id: Mapped[int] = mapped_column(
        ForeignKey("competency_definitions.id"), index=True
    )

    # not_observed|emerging|developing|proficient|mastered|needs_review|regressing
    state: Mapped[str] = mapped_column(String(16), default="not_observed")
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    distinct_context_count: Mapped[int] = mapped_column(Integer, default=0)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    weighted_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    first_observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    mastered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    algorithm_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("learner_id", "competency_id", name="uq_learner_competency"),
    )


class CEFRProjection(Base):
    """A computed CEFR snapshot derived from competency states (per skill + overall)."""
    __tablename__ = "cefr_projections"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    grammar_level: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    vocabulary_level: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    speaking_level: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    listening_level: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    reading_level: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    writing_level: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    communication_level: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    overall_level: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    algorithm_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
