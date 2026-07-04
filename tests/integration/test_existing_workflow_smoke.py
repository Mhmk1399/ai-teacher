"""Smoke tests: the existing assessment workflow must keep working.

These guard Phase 0's promise that the MVP is not broken by new architecture.
They use the in-memory DB and never call Ollama.
"""
from __future__ import annotations

import pytest

from core.models import Student, Item, Exam, ExamSession, Answer, AuditLog
from core.exam_engine import items_for_exam
from core.scoring import apply_override


def test_core_modules_import():
    # Importing the whole core package must not require a live LLM.
    import core.config, core.db, core.llm, core.prompts, core.scoring, core.exam_engine  # noqa: F401


def test_create_student_item_exam_session_answer(db):
    student = Student(full_name="Sara", l1="fa", cefr_level="A2")
    item = Item(skill="writing", cefr_level="A2", topic="Routine",
                prompt="Describe your day.", rubric={})
    db.add_all([student, item])
    db.flush()

    exam = Exam(name="A2 Writing", cefr_level="A2", skills=["writing"], item_count=1)
    db.add(exam)
    db.flush()

    picked = items_for_exam(db, exam)
    assert picked and picked[0].id == item.id

    session = ExamSession(exam_id=exam.id, student_id=student.id)
    db.add(session)
    db.flush()

    answer = Answer(session_id=session.id, item_id=item.id,
                    response_text="I wake up at seven.")
    db.add(answer)
    db.commit()

    assert db.get(Answer, answer.id).response_text == "I wake up at seven."


def test_apply_override_writes_audit_and_resolves_flag(db):
    student = Student(full_name="Ali", cefr_level="B1")
    item = Item(skill="writing", cefr_level="B1", topic="Travel",
                prompt="Tell me about a trip.", rubric={})
    db.add_all([student, item]); db.flush()
    exam = Exam(name="B1", cefr_level="B1", skills=["writing"], item_count=1)
    db.add(exam); db.flush()
    session = ExamSession(exam_id=exam.id, student_id=student.id)
    db.add(session); db.flush()
    answer = Answer(session_id=session.id, item_id=item.id,
                    response_text="...", flagged_for_review=True)
    db.add(answer); db.commit()

    updated = apply_override(db, answer_id=answer.id, reviewer_id="phd",
                             band="B1", scores={"task_achievement": 4}, note="ok")

    assert updated.reviewer_override_band == "B1"
    assert updated.flagged_for_review is False
    audits = db.query(AuditLog).filter_by(action="override_score").all()
    assert len(audits) == 1
