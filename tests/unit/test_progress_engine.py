"""Deterministic progress engine — the non-negotiable mastery rules (ADR-005)."""
from __future__ import annotations

from datetime import datetime, timedelta

from core.competency.models import CompetencyDefinition, EvidenceObservation
from core.progress.engine import compute_stats

BASE = datetime(2026, 1, 1)


def comp(**kw) -> CompetencyDefinition:
    defaults = dict(
        code="GR-B1-09", name="First Conditional", domain="grammar",
        cefr_level_hint="B1", evidence_required=5, accuracy_threshold=0.8,
        contexts_required=2,
    )
    defaults.update(kw)
    return CompetencyDefinition(**defaults)


def obs(correctness, *, confidence=0.9, context="grammar", status="pending",
        outcome=None, override=None, n=0):
    if outcome is None:
        outcome = "correct" if correctness >= 0.75 else "incorrect"
    return EvidenceObservation(
        learner_id=1, competency_id=1, source_type="exam_answer",
        outcome=outcome, correctness_score=correctness, evaluator_confidence=confidence,
        evidence_weight=confidence, context_key=context, human_review_status=status,
        human_override=override, observed_at=BASE + timedelta(days=n),
    )


def test_rule1_one_observation_never_masters():
    stats = compute_stats([obs(1.0)], comp())
    assert stats.state != "mastered"
    assert stats.valid_evidence_count == 1


def test_rule2_five_correct_one_context_fails_two_context_rule():
    obns = [obs(1.0, context="grammar", n=i) for i in range(5)]
    stats = compute_stats(obns, comp())
    assert stats.distinct_context_count == 1
    assert stats.state != "mastered"  # accuracy + count ok, but contexts < 2
    assert stats.state == "proficient"


def test_rule3_diverse_evidence_can_master():
    obns = [obs(1.0, context="grammar", n=0), obs(1.0, context="writing", n=1),
            obs(1.0, context="conversation", n=2), obs(1.0, context="grammar", n=3),
            obs(1.0, context="writing", n=4)]
    stats = compute_stats(obns, comp())
    assert stats.valid_evidence_count == 5
    assert stats.distinct_context_count == 3
    assert stats.state == "mastered"
    assert stats.mastered is True


def test_rule4_negative_evidence_lowers_accuracy():
    good = [obs(1.0, context="grammar", n=0), obs(1.0, context="writing", n=1)]
    high = compute_stats(good, comp()).weighted_accuracy
    with_bad = compute_stats(good + [obs(0.0, context="conversation", n=2)], comp())
    assert with_bad.weighted_accuracy < high


def test_rule5_rejected_evidence_is_excluded():
    obns = [obs(1.0, context="grammar", n=0), obs(1.0, context="writing", n=1),
            obs(1.0, context="conversation", n=2), obs(1.0, context="grammar", n=3),
            obs(0.0, context="writing", n=4, status="rejected")]
    stats = compute_stats(obns, comp())
    assert stats.evidence_count == 5
    assert stats.valid_evidence_count == 4
    assert stats.weighted_accuracy == 1.0  # the failing one was excluded


def test_overridden_evidence_uses_human_outcome():
    # AI said incorrect, human overrides to correct.
    obns = [obs(0.0, context="grammar", n=0, status="overridden",
                override={"outcome": "correct", "correctness_score": 1.0})]
    stats = compute_stats(obns, comp())
    assert stats.weighted_accuracy == 1.0


def test_regressing_when_recent_evidence_drops():
    obns = [obs(1.0, context="grammar", n=0), obs(1.0, context="writing", n=1),
            obs(1.0, context="conversation", n=2),
            obs(0.0, context="grammar", n=3), obs(0.0, context="writing", n=4)]
    stats = compute_stats(obns, comp(accuracy_threshold=0.5))
    assert stats.state == "regressing"


def test_no_evidence_is_not_observed():
    stats = compute_stats([], comp())
    assert stats.state == "not_observed"
