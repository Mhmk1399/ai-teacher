"""End-to-end vertical slice: Answer -> evidence -> projection -> CEFR -> review."""
from __future__ import annotations

import json

from core.ai import FakeProvider
from core.competency.models import CEFRProjection, EvidenceObservation, LearnerCompetency
from core.competency.repository import get_active_competencies, review_observation
from core.evidence.pipeline import process_answer
from core.models import Answer, Exam, ExamSession, Item, Student
from core.progress.cefr import compute_cefr
from core.progress.engine import rebuild_competency
from core.seed import load_competency_catalog


def _answer(db, response="If it rains, I will stay home."):
    student = Student(full_name="Sara", cefr_level="A2")
    item = Item(skill="writing", cefr_level="B1", topic="Plans",
                prompt="What will you do this weekend?", rubric={}, format="text")
    db.add_all([student, item]); db.flush()
    exam = Exam(name="B1", cefr_level="B1", skills=["writing"], item_count=1)
    db.add(exam); db.flush()
    sess = ExamSession(exam_id=exam.id, student_id=student.id)
    db.add(sess); db.flush()
    ans = Answer(session_id=sess.id, item_id=item.id, response_text=response)
    db.add(ans); db.commit(); db.refresh(ans)
    return student, item, ans


def test_seed_catalog_loads_with_valid_prerequisites(db):
    n = load_competency_catalog(db, "grammar")
    assert n == 12
    comps = get_active_competencies(db)
    assert len(comps) == 12
    codes = {c.code for c in comps}
    assert "GR-B1-09" in codes and "GR-C2-01" in codes
    # C2 uses performance descriptors, not just grammar bullet lists.
    c2 = next(c for c in comps if c.code == "GR-C2-01")
    assert c2.performance_descriptors


def test_process_answer_creates_evidence_and_projection(db):
    load_competency_catalog(db, "grammar")
    student, item, ans = _answer(db)
    comps = get_active_competencies(db)
    by_code = {c.code: c for c in comps}
    payload = json.dumps({"observations": [
        {"competency_code": "GR-B1-09", "outcome": "correct",
         "correctness_score": 0.95, "confidence": 0.85,
         "evidence_excerpt": "If it rains, I will stay home"}]})

    res = process_answer(db, FakeProvider(responses=[payload]), ans.id)

    assert res.outcome.success
    assert len(res.outcome.observations) == 1
    lc = db.query(LearnerCompetency).filter_by(
        learner_id=student.id, competency_id=by_code["GR-B1-09"].id).one()
    # One observation can never be mastery.
    assert lc.state != "mastered"
    assert lc.valid_evidence_count == 1
    assert res.cefr is not None


def test_rebuild_is_deterministic(db):
    """Rule 6: rebuilding yields the same projection."""
    load_competency_catalog(db, "grammar")
    student, item, ans = _answer(db)
    comps = get_active_competencies(db)
    code_id = {c.code: c.id for c in comps}
    payload = json.dumps({"observations": [
        {"competency_code": "GR-B1-09", "outcome": "partially_correct",
         "correctness_score": 0.6, "confidence": 0.7}]})
    process_answer(db, FakeProvider(responses=[payload]), ans.id)

    cid = code_id["GR-B1-09"]
    first = rebuild_competency(db, student.id, cid)
    snapshot = (first.state, first.weighted_accuracy, first.confidence,
                first.valid_evidence_count)
    for _ in range(3):
        again = rebuild_competency(db, student.id, cid)
        assert (again.state, again.weighted_accuracy, again.confidence,
                again.valid_evidence_count) == snapshot


def test_rejecting_observation_rebuilds_projection(db):
    """Expert rejects an observation -> projection excludes it on rebuild."""
    load_competency_catalog(db, "grammar")
    student, item, ans = _answer(db)
    comps = get_active_competencies(db)
    payload = json.dumps({"observations": [
        {"competency_code": "GR-B1-09", "outcome": "correct",
         "correctness_score": 1.0, "confidence": 0.9}]})
    res = process_answer(db, FakeProvider(responses=[payload]), ans.id)
    obs = res.outcome.observations[0]

    lc = review_observation(db, obs.id, status="rejected", reviewer_id="phd")
    assert lc.valid_evidence_count == 0
    assert lc.state in ("not_observed",)


def test_cefr_cannot_exceed_competency_evidence(db):
    """Rule 9: CEFR is bounded by mastered competencies."""
    load_competency_catalog(db, "grammar")
    student, item, ans = _answer(db)
    # No observations at all -> no mastery -> overall below A1 (None).
    res = compute_cefr(db, student.id)
    assert res.overall_level is None

    # A single correct B1 observation cannot push CEFR to B1 (not mastered).
    comps = get_active_competencies(db)
    payload = json.dumps({"observations": [
        {"competency_code": "GR-B1-09", "outcome": "correct",
         "correctness_score": 1.0, "confidence": 0.9}]})
    process_answer(db, FakeProvider(responses=[payload]), ans.id)
    res2 = compute_cefr(db, student.id)
    assert res2.overall_level is None  # still nothing mastered


def test_cefr_reaches_a1_when_a1_competencies_mastered(db):
    """Complement to rule 9: the projection CAN produce a level from real mastery."""
    from datetime import datetime, timedelta
    load_competency_catalog(db, "grammar")
    student = Student(full_name="Mastery", cefr_level="A1")
    db.add(student); db.commit(); db.refresh(student)
    comps = {c.code: c for c in get_active_competencies(db)}

    # Master the three A1 competencies with diverse, confident evidence.
    for code in ("GR-A1-01", "GR-A1-02", "GR-A1-03"):
        comp = comps[code]
        for i, ctx in enumerate(["grammar", "writing", "conversation",
                                  "grammar", "writing", "conversation"]):
            db.add(EvidenceObservation(
                learner_id=student.id, competency_id=comp.id, source_type="exam_answer",
                source_id=1000 + i, context_key=ctx, outcome="correct",
                correctness_score=1.0, evaluator_confidence=0.95, evidence_weight=0.95,
                human_review_status="pending",
                observed_at=datetime(2026, 1, 1) + timedelta(days=i)))
    db.commit()

    from core.progress.engine import rebuild_learner
    rebuild_learner(db, student.id)
    res = compute_cefr(db, student.id)
    assert res.overall_level == "A1"  # A1 passed, A2+ not -> contiguous stop at A1
