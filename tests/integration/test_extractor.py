"""Evidence extractor with the fake provider (no Ollama)."""
from __future__ import annotations

import json

import pytest

from core.ai import FakeProvider
from core.competency.models import EvaluationRun, EvidenceObservation
from core.competency.repository import upsert_competency
from core.competency.schemas import CompetencyDefinitionIn
from core.evidence.extractor import extract_observations_for_answer
from core.models import Student


def _seed_two_competencies(db):
    upsert_competency(db, CompetencyDefinitionIn(
        code="GR-A1-01", name="Present simple", domain="grammar", cefr_level_hint="A1"))
    upsert_competency(db, CompetencyDefinitionIn(
        code="GR-B1-09", name="First conditional", domain="grammar", cefr_level_hint="B1"))
    from core.competency.repository import get_active_competencies
    return get_active_competencies(db)


def _student(db):
    s = Student(full_name="Test", cefr_level="A2")
    db.add(s); db.commit(); db.refresh(s)
    return s


def test_valid_output_creates_observations_and_run(db):
    comps = _seed_two_competencies(db)
    s = _student(db)
    payload = json.dumps({"observations": [
        {"competency_code": "GR-A1-01", "outcome": "correct",
         "correctness_score": 0.9, "confidence": 0.8,
         "evidence_excerpt": "I wake up at seven", "explanation": "ok"},
    ]})
    provider = FakeProvider(responses=[payload])

    out = extract_observations_for_answer(
        db, provider, learner_id=s.id, candidate_competencies=comps,
        student_response="I wake up at seven.", source_type="exam_answer", source_id=42)

    assert out.success
    assert len(out.observations) == 1
    assert out.observations[0].outcome == "correct"
    assert out.observations[0].evaluation_run_id == out.evaluation_run.id
    run = db.get(EvaluationRun, out.evaluation_run.id)
    assert run.success and run.model_provider == "fake"


def test_malformed_json_records_failed_run_and_no_observations(db):
    """Rule 7: malformed AI output must not update progress."""
    comps = _seed_two_competencies(db)
    s = _student(db)
    provider = FakeProvider(responses=["this is not json {{{"])

    out = extract_observations_for_answer(
        db, provider, learner_id=s.id, candidate_competencies=comps,
        student_response="hello", source_type="exam_answer", source_id=7)

    assert not out.success
    assert "schema_validation_failed" in out.error
    assert out.observations == []
    assert db.query(EvidenceObservation).count() == 0
    assert db.get(EvaluationRun, out.evaluation_run.id).success is False


def test_schema_violation_extra_field_is_rejected(db):
    comps = _seed_two_competencies(db)
    s = _student(db)
    # correctness_score out of range -> Pydantic rejects.
    bad = json.dumps({"observations": [
        {"competency_code": "GR-A1-01", "outcome": "correct",
         "correctness_score": 5.0, "confidence": 0.8}]})
    out = extract_observations_for_answer(
        db, provider=FakeProvider(responses=[bad]), learner_id=s.id,
        candidate_competencies=comps, student_response="x", source_id=1)
    assert not out.success
    assert db.query(EvidenceObservation).count() == 0


def test_unknown_codes_are_skipped_not_invented(db):
    comps = _seed_two_competencies(db)
    s = _student(db)
    payload = json.dumps({"observations": [
        {"competency_code": "GR-ZZ-99", "outcome": "correct",
         "correctness_score": 1.0, "confidence": 0.9}]})
    out = extract_observations_for_answer(
        db, FakeProvider(responses=[payload]), learner_id=s.id,
        candidate_competencies=comps, student_response="x", source_id=1)
    assert out.success
    assert out.observations == []
    assert out.skipped_unknown_codes == ["GR-ZZ-99"]


def test_reprocessing_same_source_does_not_duplicate(db):
    comps = _seed_two_competencies(db)
    s = _student(db)
    payload = json.dumps({"observations": [
        {"competency_code": "GR-A1-01", "outcome": "correct",
         "correctness_score": 0.9, "confidence": 0.8}]})
    for _ in range(3):
        extract_observations_for_answer(
            db, FakeProvider(responses=[payload]), learner_id=s.id,
            candidate_competencies=comps, student_response="x",
            source_type="exam_answer", source_id=99)
    # Pending observations for the same source+evaluator are replaced, not stacked.
    assert db.query(EvidenceObservation).filter_by(source_id=99).count() == 1


def test_provider_error_records_failed_run(db):
    """Rule 8: a failing provider (e.g. Ollama down) is handled, not crashing."""
    comps = _seed_two_competencies(db)
    s = _student(db)
    out = extract_observations_for_answer(
        db, FakeProvider(raise_error=True), learner_id=s.id,
        candidate_competencies=comps, student_response="x", source_id=1)
    assert not out.success
    assert "provider_error" in out.error
    assert db.query(EvidenceObservation).count() == 0
