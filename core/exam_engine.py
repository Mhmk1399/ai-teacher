"""Exam assembly: given a level + skills, pick N active items deterministically."""
from __future__ import annotations
import random
from sqlalchemy.orm import Session
from sqlalchemy import select

from core.models import Item, Exam


def generate_exam(
    db: Session,
    *,
    name: str,
    cefr_level: str,
    skills: list[str],
    item_count: int = 5,
    fmt: str = "text",
    description: str | None = None,
    seed: int | None = None,
) -> Exam:
    """Pick ``item_count`` active items matching the criteria and persist as an Exam."""
    rng = random.Random(seed) if seed is not None else random

    pool = db.execute(
        select(Item).where(
            Item.cefr_level == cefr_level,
            Item.skill.in_(skills),
            Item.active == True,  # noqa: E712
        )
    ).scalars().all()

    if not pool:
        raise ValueError(
            f"No active items found for level={cefr_level}, skills={skills}. "
            "Add items first via the Items page."
        )

    chosen = rng.sample(pool, k=min(item_count, len(pool)))
    exam = Exam(
        name=name,
        cefr_level=cefr_level,
        skills=skills,
        item_count=len(chosen),
        format=fmt,
        description=description,
    )
    db.add(exam)
    db.flush()

    # Snapshot the chosen item ids onto the exam (Exam doesn't have an items rel by design — flat JSON for MVP).
    from sqlalchemy import JSON  # noqa
    # We just store as a transient field via a tiny shim — Exam has no items relation;
    # instead, ExamSession will materialize them at session-start time. Keep chosen in memory for the caller.
    db.commit()
    db.refresh(exam)

    # Attach as an attribute for the caller; not persisted.
    setattr(exam, "_selected_items", chosen)
    return exam


def items_for_exam(db: Session, exam: Exam) -> list[Item]:
    """Pick items for an existing exam (re-randomize each session for now)."""
    pool = db.execute(
        select(Item).where(
            Item.cefr_level == exam.cefr_level,
            Item.skill.in_(exam.skills),
            Item.active == True,  # noqa: E712
        )
    ).scalars().all()
    if not pool:
        return []
    rng = random.Random()
    return rng.sample(pool, k=min(exam.item_count, len(pool)))
