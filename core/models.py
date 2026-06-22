"""SQLAlchemy ORM models for the Lingua Nova exam machine.

Naming notes
------------
- ``Item``  = a single exam question/prompt authored by the PhD master
- ``Exam``  = a template that selects N items for a given level + skill
- ``ExamSession`` = one student's run of an exam (text MVP, voice-ready)
- ``Answer`` = one student response to one item, with score + audit trail
- ``AuditLog`` = append-only log of every meaningful action (override, edit…)
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    ForeignKey, String, Text, JSON, Float, Integer, DateTime, Boolean,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------- Master data ----------

class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(200))
    l1: Mapped[str] = mapped_column(String(8), default="fa")
    cefr_level: Mapped[str] = mapped_column(String(2), default="A2", index=True)
    goal: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sessions: Mapped[list["ExamSession"]] = relationship(back_populates="student", cascade="all, delete-orphan")


class Item(Base):
    """A single exam question/prompt. The PhD master's content unit."""
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    skill: Mapped[str] = mapped_column(String(16), index=True)            # speaking | writing | listening | reading
    cefr_level: Mapped[str] = mapped_column(String(2), index=True)
    topic: Mapped[str] = mapped_column(String(120))
    prompt: Mapped[str] = mapped_column(Text)                              # the question
    expected_patterns: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # linguistic features expected
    sample_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)    # model answer for the PhD master
    rubric: Mapped[dict] = mapped_column(JSON, default=dict)               # scoring rubric per criterion
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    format: Mapped[str] = mapped_column(String(8), default="text")        # text | voice
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    answers: Mapped[list["Answer"]] = relationship(back_populates="item")

    __table_args__ = (
        Index("ix_items_skill_level", "skill", "cefr_level", "active"),
    )


# ---------- Exam templates & runs ----------

class Exam(Base):
    __tablename__ = "exams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    cefr_level: Mapped[str] = mapped_column(String(2), index=True)
    skills: Mapped[list] = mapped_column(JSON)             # e.g. ["speeking","writing"]
    item_count: Mapped[int] = mapped_column(Integer, default=5)
    format: Mapped[str] = mapped_column(String(8), default="text")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sessions: Mapped[list["ExamSession"]] = relationship(back_populates="exam")


class ExamSession(Base):
    __tablename__ = "exam_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | finished | abandoned
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    final_band: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    exam: Mapped["Exam"] = relationship(back_populates="sessions")
    student: Mapped["Student"] = relationship(back_populates="sessions")
    answers: Mapped[list["Answer"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    response_text: Mapped[str] = mapped_column(Text)
    response_audio_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    raw_llm_output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    band: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    scores: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)   # criterion-level scores
    feedback_student: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_internal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    flagged_for_review: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_override_band: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    reviewer_override_scores: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    reviewer_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    item: Mapped["Item"] = relationship(back_populates="answers")
    session: Mapped["ExamSession"] = relationship(back_populates="answers")


class AuditLog(Base):
    """Append-only log. The 'fine-tune dataset' grows out of overrides."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(64))                 # create_item | override_score | …
    entity_type: Mapped[str] = mapped_column(String(32))           # item | answer | student | …
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
