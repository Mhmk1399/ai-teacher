"""Deterministic competency progress engine.

Given a learner's raw ``EvidenceObservation`` rows for a competency, compute a
``LearnerCompetency`` projection: state, accuracy, confidence, and a
human-readable reason. The formula lives here in code (ADR-005), not in prompts.

Key invariants (covered by tests):
- One observation can never produce ``mastered`` (count + context gates).
- Rejected evidence is excluded; human-accepted/overridden evidence is weighted
  up and can use the human's corrected outcome.
- The projection is a pure function of (valid observations, thresholds, config,
  algorithm_version): rebuilding yields identical results.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.competency.models import (
    CompetencyDefinition,
    EvidenceObservation,
    LearnerCompetency,
)

ALGORITHM_VERSION = "pe-v1"

# Outcome -> fallback correctness if the AI omitted a numeric score (defensive).
_OUTCOME_FALLBACK = {
    "correct": 1.0,
    "partially_correct": 0.5,
    "incorrect": 0.0,
    "not_demonstrated": 0.0,
    "uncertain": 0.0,
}
_REJECTED = "rejected"
_HUMAN_TRUSTED = ("accepted", "overridden")


@dataclass(frozen=True)
class ProgressConfig:
    """Tunable, explicit thresholds. Persisted decisions reference these."""
    min_projection_confidence: float = 0.5
    human_weight_multiplier: float = 1.5     # accepted/overridden evidence counts more
    developing_accuracy: float = 0.5         # below proficient, above emerging
    regression_recent_max: float = 0.5       # recent accuracy under this => regressing
    regression_window: int = 2               # how many most-recent obs define "recent"


DEFAULT_CONFIG = ProgressConfig()


@dataclass
class _Stat:
    weight: float
    correctness: float
    context_key: str
    observed_at: datetime


def _effective(obs: EvidenceObservation, config: ProgressConfig) -> _Stat:
    """Resolve one observation into (weight, correctness), honoring human overrides."""
    outcome = obs.outcome
    correctness = obs.correctness_score
    base_weight = max(0.05, obs.evidence_weight or obs.evaluator_confidence or 0.05)

    if obs.human_review_status == "overridden" and isinstance(obs.human_override, dict):
        ov = obs.human_override
        if ov.get("outcome") is not None:
            outcome = ov["outcome"]
        if ov.get("correctness_score") is not None:
            correctness = float(ov["correctness_score"])

    if correctness is None:
        correctness = _OUTCOME_FALLBACK.get(outcome, 0.0)

    weight = base_weight
    if obs.human_review_status in _HUMAN_TRUSTED:
        weight *= config.human_weight_multiplier
    return _Stat(
        weight=weight,
        correctness=float(correctness),
        context_key=obs.context_key or "default",
        observed_at=obs.observed_at or datetime.utcnow(),
    )


@dataclass
class ProjectionStats:
    state: str
    evidence_count: int
    valid_evidence_count: int
    distinct_context_count: int
    accuracy: float
    weighted_accuracy: float
    confidence: float
    reason: str
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    mastered: bool


def compute_stats(
    observations: list[EvidenceObservation],
    competency: CompetencyDefinition,
    config: ProgressConfig = DEFAULT_CONFIG,
) -> ProjectionStats:
    """Pure: derive the projection for one competency from its observations."""
    evidence_count = len(observations)
    valid = [o for o in observations if o.human_review_status != _REJECTED]
    valid_count = len(valid)

    if valid_count == 0:
        return ProjectionStats(
            state="not_observed", evidence_count=evidence_count, valid_evidence_count=0,
            distinct_context_count=0, accuracy=0.0, weighted_accuracy=0.0, confidence=0.0,
            reason="No valid evidence yet." if evidence_count == 0
            else "All evidence was rejected on review.",
            first_observed_at=None, last_observed_at=None, mastered=False,
        )

    stats = [_effective(o, config) for o in valid]
    total_w = sum(s.weight for s in stats)
    weighted_accuracy = sum(s.weight * s.correctness for s in stats) / total_w if total_w else 0.0
    accuracy = sum(s.correctness for s in stats) / valid_count
    distinct_contexts = len({s.context_key for s in stats})

    mean_conf = sum(max(0.05, o.evaluator_confidence or 0.0) for o in valid) / valid_count
    # Confidence grows with evidence volume but is capped at 1.0. A single
    # observation yields a deliberately low projection confidence.
    coverage = min(1.0, valid_count / max(1, competency.evidence_required))
    confidence = round(mean_conf * coverage, 4)

    ordered = sorted(stats, key=lambda s: s.observed_at)
    first_at = ordered[0].observed_at
    last_at = ordered[-1].observed_at
    recent = ordered[-config.regression_window:] if len(ordered) >= config.regression_window else []
    recent_accuracy = (sum(s.correctness for s in recent) / len(recent)) if recent else None

    thr = competency.accuracy_threshold
    req = competency.evidence_required
    ctx_req = competency.contexts_required

    gate_count = valid_count >= req
    gate_acc = weighted_accuracy >= thr
    gate_ctx = distinct_contexts >= ctx_req
    gate_conf = confidence >= config.min_projection_confidence
    mastery_gates = gate_count and gate_acc and gate_ctx and gate_conf

    # Regression is evaluated BEFORE mastery: a clear downward recent trend blocks
    # a "mastered" verdict even when cumulative gates pass.
    regressing = (
        gate_acc and recent_accuracy is not None
        and recent_accuracy < config.regression_recent_max
    )
    mastered = mastery_gates and not regressing

    if regressing:
        state = "regressing"
        reason = (
            f"Regressing: overall accuracy {weighted_accuracy:.2f} is high but the "
            f"{len(recent)} most recent observations average {recent_accuracy:.2f}."
        )
    elif mastered:
        state = "mastered"
        reason = (
            f"Mastered: {valid_count}/{req} evidence, weighted accuracy "
            f"{weighted_accuracy:.2f}>={thr:.2f}, {distinct_contexts}/{ctx_req} contexts, "
            f"confidence {confidence:.2f}>={config.min_projection_confidence:.2f}."
        )
    elif gate_count and not gate_conf:
        state = "needs_review"
        reason = (
            f"Needs review: {valid_count} observations gathered but projection "
            f"confidence {confidence:.2f} < {config.min_projection_confidence:.2f} "
            f"(low/uncertain evidence)."
        )
    elif gate_acc:
        missing = []
        if not gate_count:
            missing.append(f"evidence {valid_count}/{req}")
        if not gate_ctx:
            missing.append(f"contexts {distinct_contexts}/{ctx_req}")
        if not gate_conf:
            missing.append(f"confidence {confidence:.2f}/{config.min_projection_confidence:.2f}")
        state = "proficient"
        reason = (
            f"Proficient: accuracy {weighted_accuracy:.2f}>={thr:.2f} but not yet "
            f"mastered (needs {', '.join(missing) or 'more evidence'})."
        )
    elif weighted_accuracy >= config.developing_accuracy:
        state = "developing"
        reason = (
            f"Developing: accuracy {weighted_accuracy:.2f} (< {thr:.2f}) across "
            f"{valid_count} observation(s)."
        )
    else:
        state = "emerging"
        reason = (
            f"Emerging: accuracy {weighted_accuracy:.2f} is low across "
            f"{valid_count} observation(s)."
        )

    return ProjectionStats(
        state=state, evidence_count=evidence_count, valid_evidence_count=valid_count,
        distinct_context_count=distinct_contexts, accuracy=round(accuracy, 4),
        weighted_accuracy=round(weighted_accuracy, 4), confidence=confidence,
        reason=reason, first_observed_at=first_at, last_observed_at=last_at,
        mastered=mastered,
    )


def rebuild_competency(
    db: Session,
    learner_id: int,
    competency_id: int,
    config: ProgressConfig = DEFAULT_CONFIG,
) -> LearnerCompetency:
    """Recompute and upsert the LearnerCompetency projection for one pair."""
    competency = db.get(CompetencyDefinition, competency_id)
    if competency is None:
        raise ValueError(f"No CompetencyDefinition with id={competency_id}")

    observations = db.execute(
        select(EvidenceObservation).where(
            EvidenceObservation.learner_id == learner_id,
            EvidenceObservation.competency_id == competency_id,
        )
    ).scalars().all()

    stats = compute_stats(observations, competency, config)

    lc = db.execute(
        select(LearnerCompetency).where(
            LearnerCompetency.learner_id == learner_id,
            LearnerCompetency.competency_id == competency_id,
        )
    ).scalar_one_or_none()
    if lc is None:
        lc = LearnerCompetency(learner_id=learner_id, competency_id=competency_id)
        db.add(lc)

    lc.state = stats.state
    lc.evidence_count = stats.evidence_count
    lc.valid_evidence_count = stats.valid_evidence_count
    lc.distinct_context_count = stats.distinct_context_count
    lc.accuracy = stats.accuracy
    lc.weighted_accuracy = stats.weighted_accuracy
    lc.confidence = stats.confidence
    lc.reason = stats.reason
    lc.first_observed_at = stats.first_observed_at
    lc.last_observed_at = stats.last_observed_at
    lc.mastered_at = stats.last_observed_at if stats.mastered else None
    lc.algorithm_version = ALGORITHM_VERSION
    lc.computed_at = datetime.utcnow()

    db.commit()
    db.refresh(lc)
    return lc


def rebuild_learner(
    db: Session,
    learner_id: int,
    config: ProgressConfig = DEFAULT_CONFIG,
) -> list[LearnerCompetency]:
    """Rebuild every competency for which this learner has any observation."""
    comp_ids = db.execute(
        select(EvidenceObservation.competency_id)
        .where(EvidenceObservation.learner_id == learner_id)
        .distinct()
    ).scalars().all()
    return [rebuild_competency(db, learner_id, cid, config) for cid in comp_ids]
