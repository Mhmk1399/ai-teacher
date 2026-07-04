"""Repository + small services for the competency catalog and reviews.

Keeps SQLAlchemy access and catalog-integrity validation out of UI code.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.competency.models import (
    CompetencyDefinition,
    CompetencyPrerequisite,
    EvidenceObservation,
    LearnerCompetency,
)
from core.competency.schemas import CompetencyDefinitionIn
from core.models import AuditLog
from core.progress.engine import DEFAULT_CONFIG, ProgressConfig, rebuild_competency

_VALID_REVIEW = {"pending", "accepted", "rejected", "overridden"}


class CatalogError(ValueError):
    pass


# ---------------- Catalog CRUD ----------------

def get_active_competencies(
    db: Session, *, domain: str | None = None
) -> list[CompetencyDefinition]:
    stmt = select(CompetencyDefinition).where(CompetencyDefinition.active == True)  # noqa: E712
    if domain:
        stmt = stmt.where(CompetencyDefinition.domain == domain)
    return list(db.execute(stmt.order_by(CompetencyDefinition.code)).scalars().all())


def get_by_code(db: Session, code: str) -> CompetencyDefinition | None:
    return db.execute(
        select(CompetencyDefinition).where(CompetencyDefinition.code == code.strip().upper())
    ).scalar_one_or_none()


def upsert_competency(
    db: Session, data: CompetencyDefinitionIn, *, created_by: str = "expert"
) -> CompetencyDefinition:
    """Create or update a competency by code. Validates the payload (Pydantic).

    Prerequisite wiring is done by ``link_prerequisites`` after all codes exist.
    """
    existing = get_by_code(db, data.code)
    fields = dict(
        code=data.code, name=data.name, domain=data.domain, subdomain=data.subdomain,
        skill=data.skill, description=data.description, cefr_level_hint=data.cefr_level_hint,
        performance_descriptors=data.performance_descriptors,
        positive_patterns=data.positive_patterns, negative_patterns=data.negative_patterns,
        exceptions=data.exceptions, evidence_required=data.evidence_required,
        accuracy_threshold=data.accuracy_threshold, contexts_required=data.contexts_required,
        active=data.active, version=data.version,
    )
    if existing is None:
        comp = CompetencyDefinition(created_by=created_by, **fields)
        db.add(comp)
        action = "create_competency"
    else:
        for k, v in fields.items():
            setattr(existing, k, v)
        comp = existing
        action = "update_competency"
    db.flush()
    db.add(AuditLog(actor=created_by, action=action, entity_type="competency",
                    entity_id=comp.id, payload={"code": comp.code}))
    db.commit()
    db.refresh(comp)
    return comp


def link_prerequisites(
    db: Session, code: str, prerequisite_codes: list[str], *, relationship_type: str = "requires"
) -> None:
    """Create prerequisite edges, validating that referenced codes exist and no self-loop."""
    comp = get_by_code(db, code)
    if comp is None:
        raise CatalogError(f"Unknown competency code: {code}")
    for pre_code in prerequisite_codes:
        if pre_code.strip().upper() == comp.code:
            raise CatalogError(f"Competency {comp.code} cannot be its own prerequisite")
        pre = get_by_code(db, pre_code)
        if pre is None:
            raise CatalogError(f"Prerequisite {pre_code} for {comp.code} does not exist")
        exists = db.execute(
            select(CompetencyPrerequisite).where(
                CompetencyPrerequisite.competency_id == comp.id,
                CompetencyPrerequisite.prerequisite_competency_id == pre.id,
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(CompetencyPrerequisite(
                competency_id=comp.id, prerequisite_competency_id=pre.id,
                relationship_type=relationship_type,
            ))
    db.commit()


# ---------------- Observation review (expert authority) ----------------

def review_observation(
    db: Session,
    observation_id: int,
    *,
    status: str,
    reviewer_id: str = "expert",
    override: dict | None = None,
    config: ProgressConfig = DEFAULT_CONFIG,
) -> LearnerCompetency:
    """Set an observation's review status (and optional override), then rebuild.

    Raw evidence is never deleted — only its status/override changes — so the
    projection can always be rebuilt (ADR-007). Returns the updated projection.
    """
    if status not in _VALID_REVIEW:
        raise ValueError(f"Invalid review status: {status}")
    obs = db.get(EvidenceObservation, observation_id)
    if obs is None:
        raise ValueError(f"No EvidenceObservation with id={observation_id}")

    obs.human_review_status = status
    obs.human_override = override if status == "overridden" else None
    db.add(AuditLog(actor=reviewer_id, action="review_observation",
                    entity_type="evidence_observation", entity_id=obs.id,
                    payload={"status": status, "override": override}))
    db.flush()

    lc = rebuild_competency(db, obs.learner_id, obs.competency_id, config)
    return lc
