"""Orchestration: existing Answer -> competency evidence -> projection -> CEFR.

This is the vertical slice's seam into the existing assessment data. It does not
change scoring; it runs *alongside* it. Call it after an answer exists.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.ai.provider import LanguageModelProvider
from core.competency.models import CEFRProjection, LearnerCompetency
from core.competency.repository import get_active_competencies
from core.evidence.extractor import ExtractionOutcome, extract_observations_for_answer
from core.models import Answer, ExamSession, Item
from core.progress.cefr import rebuild_cefr_projection
from core.progress.engine import DEFAULT_CONFIG, ProgressConfig, rebuild_learner

log = logging.getLogger("lingua.pipeline")


@dataclass
class AnswerProcessingResult:
    outcome: ExtractionOutcome
    projections: list[LearnerCompetency]
    cefr: CEFRProjection | None


def process_answer(
    db: Session,
    provider: LanguageModelProvider,
    answer_id: int,
    *,
    domain: str | None = None,
    config: ProgressConfig = DEFAULT_CONFIG,
) -> AnswerProcessingResult:
    """Extract competency evidence from one Answer and refresh the learner's map."""
    answer = db.get(Answer, answer_id)
    if answer is None:
        raise ValueError(f"No Answer with id={answer_id}")
    item = db.get(Item, answer.item_id)
    session = db.get(ExamSession, answer.session_id)
    if item is None or session is None:
        raise ValueError(f"Answer {answer_id} has a missing item/session")

    learner_id = session.student_id
    candidates = get_active_competencies(db, domain=domain)
    if not candidates:
        log.info("no active competencies; skipping extraction for answer=%s", answer_id)
        return AnswerProcessingResult(
            outcome=ExtractionOutcome(evaluation_run=None, error="no_active_competencies"),  # type: ignore[arg-type]
            projections=[], cefr=None,
        )

    # Context diversity is keyed on the item's skill so repeating the *same*
    # kind of exercise does not inflate context count (domain Rule 3).
    outcome = extract_observations_for_answer(
        db, provider,
        learner_id=learner_id,
        candidate_competencies=candidates,
        student_response=answer.response_text,
        source_type="exam_answer",
        source_id=answer.id,
        activity_type="exam",
        context_key=item.skill or "exam",
        modality=item.format or "text",
        item_prompt=item.prompt,
        cefr_level=item.cefr_level,
    )

    if not outcome.success:
        # Extraction failed/invalid: progress is intentionally NOT updated.
        return AnswerProcessingResult(outcome=outcome, projections=[], cefr=None)

    projections = rebuild_learner(db, learner_id, config)
    cefr = rebuild_cefr_projection(db, learner_id)
    return AnswerProcessingResult(outcome=outcome, projections=projections, cefr=cefr)
