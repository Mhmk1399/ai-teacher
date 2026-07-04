"""CEFR projection — derived from competency mastery (ADR-002).

A learner's CEFR level per domain is the highest level at which they have
mastered a sufficient fraction of that level's competencies *and* every lower
level. Because it counts only ``mastered`` competencies from the catalog, the
projected level can never exceed what the evidence + mastery rules support.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.competency.models import (
    CEFRProjection,
    CompetencyDefinition,
    LearnerCompetency,
)

CEFR_ALGORITHM_VERSION = "cefr-v1"
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}

# Which competency `domain` feeds which CEFRProjection column.
_DOMAIN_TO_FIELD = {
    "grammar": "grammar_level",
    "vocabulary": "vocabulary_level",
    "speaking": "speaking_level",
    "listening": "listening_level",
    "reading": "reading_level",
    "writing": "writing_level",
    "communication": "communication_level",
}

_MASTERED = {"mastered"}


@dataclass
class DomainResult:
    level: str | None
    detail: str
    confidence: float


@dataclass
class CEFRResult:
    domain_levels: dict[str, str | None]
    overall_level: str | None
    confidence: float
    explanation: str
    per_field: dict[str, str | None] = field(default_factory=dict)


def _domain_level(
    by_level: dict[str, list[CompetencyDefinition]],
    mastered_ids: set[int],
    pass_fraction: float,
) -> DomainResult:
    achieved: str | None = None
    parts: list[str] = []
    counted = 0
    for lvl in LEVELS:
        comps = by_level.get(lvl, [])
        if not comps:
            # No catalog competencies at this level: it cannot block higher
            # levels, but also cannot be "achieved". Skip transparently.
            continue
        n_mastered = sum(1 for c in comps if c.id in mastered_ids)
        frac = n_mastered / len(comps)
        parts.append(f"{lvl}: {n_mastered}/{len(comps)}")
        if frac >= pass_fraction:
            achieved = lvl
            counted += n_mastered
        else:
            break  # contiguous: stop at first unmet level
    total_mastered = len(mastered_ids)
    confidence = round(counted / total_mastered, 4) if total_mastered else 0.0
    return DomainResult(level=achieved, detail="; ".join(parts) or "(no competencies)",
                        confidence=confidence if achieved else 0.0)


def compute_cefr(
    db: Session,
    learner_id: int,
    *,
    pass_fraction: float = 0.6,
) -> CEFRResult:
    """Pure-ish read: compute (but do not persist) the learner's CEFR projection."""
    competencies = db.execute(
        select(CompetencyDefinition).where(CompetencyDefinition.active == True)  # noqa: E712
    ).scalars().all()

    rows = db.execute(
        select(LearnerCompetency).where(LearnerCompetency.learner_id == learner_id)
    ).scalars().all()
    mastered_ids = {r.competency_id for r in rows if r.state in _MASTERED}

    # Group competencies by domain -> level.
    by_domain: dict[str, dict[str, list[CompetencyDefinition]]] = {}
    for c in competencies:
        by_domain.setdefault(c.domain, {}).setdefault(c.cefr_level_hint, []).append(c)

    domain_levels: dict[str, str | None] = {}
    per_field: dict[str, str | None] = {}
    confidences: list[float] = []
    detail_parts: list[str] = []
    for domain, by_level in sorted(by_domain.items()):
        res = _domain_level(by_level, mastered_ids, pass_fraction)
        domain_levels[domain] = res.level
        field_name = _DOMAIN_TO_FIELD.get(domain)
        if field_name:
            per_field[field_name] = res.level
        if res.level:
            confidences.append(res.confidence)
        detail_parts.append(f"{domain} -> {res.level or 'below A1'} [{res.detail}]")

    present = [lvl for lvl in domain_levels.values() if lvl]
    # Conservative overall: a learner is reported at their weakest assessed skill.
    overall = min(present, key=lambda l: _RANK[l]) if present else None
    confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
    explanation = (
        f"Overall {overall or 'below A1'} (conservative = weakest assessed domain). "
        + " | ".join(detail_parts)
    )
    return CEFRResult(domain_levels=domain_levels, overall_level=overall,
                      confidence=confidence, explanation=explanation, per_field=per_field)


def rebuild_cefr_projection(
    db: Session,
    learner_id: int,
    *,
    pass_fraction: float = 0.6,
) -> CEFRProjection:
    """Compute and persist a fresh CEFRProjection snapshot for the learner."""
    res = compute_cefr(db, learner_id, pass_fraction=pass_fraction)
    proj = CEFRProjection(
        learner_id=learner_id,
        overall_level=res.overall_level,
        confidence=res.confidence,
        explanation=res.explanation,
        algorithm_version=CEFR_ALGORITHM_VERSION,
        computed_at=datetime.utcnow(),
    )
    for field_name, level in res.per_field.items():
        setattr(proj, field_name, level)
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj
